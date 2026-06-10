---
id: blue-green-deployment
category: deployment
title: Blue-Green Deployment
summary: We reduce downtime by maintaining two identical environments and switching
  traffic after validation.
tags:
- deployment
- blue-green
- zero-downtime
confidence: high
status: published
created_at: '2026-06-05T05:08:44.926640+00:00'
updated_at: '2026-06-05T05:08:44.926645+00:00'
---

# 概述

We deploy new releases to a green environment while blue continues serving production, then switch traffic after testing, allowing instant rollback.

# 细节

Process: 1. Blue environment serves production traffic; 2. Deploy new version to green environment; 3. Test green environment; 4. Switch traffic from blue to green; 5. Keep blue as rollback option.
