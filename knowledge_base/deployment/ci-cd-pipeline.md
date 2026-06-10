---
id: ci-cd-pipeline
category: deployment
title: CI/CD Pipeline
summary: We automate code delivery with stages from commit to production deployment,
  ensuring reliable releases.
tags:
- ci-cd
- automation
- pipelines
confidence: high
status: published
created_at: '2026-06-05T05:08:44.926659+00:00'
updated_at: '2026-06-05T05:08:44.926660+00:00'
---

# 概述

We use a pipeline that builds, tests, and deploys code automatically, triggered by commits.

# 细节

Stages: 1. Code commit triggers build; 2. Run automated tests; 3. Build artifacts (Docker images, binaries); 4. Deploy to staging; 5. Run integration tests; 6. Deploy to production.
