# Terraform and provider versions, checked 2026-10-01.

terraform {
  # ASSUMPTION (unverified): 1.5 as the floor; the module uses only long-standing HCL
  # (templatefile, base64encode, variable validation).
  required_version = ">= 1.5.0"

  required_providers {
    linode = {
      # Akamai's provider is linode/linode. 4.7.0 is the current release
      # [https://registry.terraform.io/providers/linode/linode/latest/docs, as-of 2026-10-01;
      # registry API: published 2026-09-29]. Pinned to the 4.x line it was checked against.
      source  = "linode/linode"
      version = "~> 4.7"
    }
  }
}

# The token is read from LINODE_TOKEN; it never appears in this module or its variables.
provider "linode" {}
