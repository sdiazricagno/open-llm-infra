data "aws_region" "current" {}

data "aws_ssm_parameter" "gpu_ami" {
  name = "/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-22.04/latest/ami-id"
}

locals {
  tags = merge({ "app" = "open-llm-infra", "component" = "vllm" }, var.tags)
}

resource "aws_security_group" "alb" {
  name_prefix = "${var.name}-alb-"
  vpc_id      = var.vpc_id
  tags        = local.tags

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "node" {
  name_prefix = "${var.name}-node-"
  vpc_id      = var.vpc_id
  tags        = local.tags

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name_prefix        = "${var.name}-node-"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "hf_token" {
  count = var.hf_token_ssm_parameter == "" ? 0 : 1
  statement {
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${data.aws_region.current.region}:*:parameter/${trimprefix(var.hf_token_ssm_parameter, "/")}"]
  }
}

resource "aws_iam_role_policy" "hf_token" {
  count  = var.hf_token_ssm_parameter == "" ? 0 : 1
  name   = "read-hf-token"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.hf_token[0].json
}

resource "aws_iam_instance_profile" "node" {
  name_prefix = "${var.name}-node-"
  role        = aws_iam_role.node.name
}

resource "aws_launch_template" "node" {
  name_prefix            = "${var.name}-"
  image_id               = data.aws_ssm_parameter.gpu_ami.value
  instance_type          = var.instance_type
  vpc_security_group_ids = [aws_security_group.node.id]
  update_default_version = true
  tags                   = local.tags

  user_data = base64encode(templatefile("${path.module}/user_data.sh.tftpl", {
    model                  = var.model
    max_model_len          = var.max_model_len
    vllm_image             = var.vllm_image
    hf_token_ssm_parameter = var.hf_token_ssm_parameter
    region                 = data.aws_region.current.region
  }))

  iam_instance_profile {
    arn = aws_iam_instance_profile.node.arn
  }

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = var.root_volume_gb
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  dynamic "instance_market_options" {
    for_each = var.use_spot ? [1] : []
    content {
      market_type = "spot"
      spot_options {
        instance_interruption_behavior = "terminate"
      }
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.tags, { "Name" = "${var.name}-vllm" })
  }
}

resource "aws_lb" "this" {
  name_prefix        = substr(replace(var.name, "_", "-"), 0, 6)
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.subnet_ids
  idle_timeout       = 300
  tags               = local.tags
}

resource "aws_lb_target_group" "vllm" {
  name_prefix          = substr(replace(var.name, "_", "-"), 0, 6)
  port                 = 8000
  protocol             = "HTTP"
  vpc_id               = var.vpc_id
  deregistration_delay = 60
  tags                 = local.tags

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  tags              = local.tags

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.vllm.arn
  }
}

resource "aws_autoscaling_group" "vllm" {
  name_prefix               = "${var.name}-"
  min_size                  = var.min_size
  max_size                  = var.max_size
  desired_capacity          = var.desired_capacity
  vpc_zone_identifier       = var.subnet_ids
  target_group_arns         = [aws_lb_target_group.vllm.arn]
  health_check_type         = "ELB"
  health_check_grace_period = 900

  launch_template {
    id      = aws_launch_template.node.id
    version = "$Latest"
  }

  dynamic "tag" {
    for_each = local.tags
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }
}

resource "aws_autoscaling_policy" "requests" {
  name                   = "${var.name}-requests-per-target"
  autoscaling_group_name = aws_autoscaling_group.vllm.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    target_value = var.target_requests_per_instance
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.this.arn_suffix}/${aws_lb_target_group.vllm.arn_suffix}"
    }
  }
}
