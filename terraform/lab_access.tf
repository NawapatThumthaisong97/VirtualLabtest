# Phase 14: let Tailscale users reach lab web ports (code-server etc.) through
# the router. Phase 6 only allowed SSH from the router to the lab instances.
#
# SkyPilot adds the matching ingress on sg-lab-instances itself (from
# `ports:` in the task), so only the router's egress is missing.

resource "aws_vpc_security_group_egress_rule" "ts_router_lab_web" {
  security_group_id            = aws_security_group.ts_router.id
  description                  = "Lab web ports through router"
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  referenced_security_group_id = aws_security_group.lab_instances.id
}
