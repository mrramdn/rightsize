---
type: regex
target: last_message
pattern: '\d[\d,]*\s*(?:tokens?\s*)?(?:→|->|to)\s*(?:about\s+)?~?\d[\d,]*\s*tokens|Before\s*\|\s*After'
flags: i
weight: 1
---

The final response gives the before and after token numbers ("~1,366 → ~602 tokens", "from about 1,366 to about
602 tokens", or a Before | After table).
