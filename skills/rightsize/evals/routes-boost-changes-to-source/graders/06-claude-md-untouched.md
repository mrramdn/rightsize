---
type: regex
target:
  source: file
  path: CLAUDE.md
pattern: '^# Bookings\n\n- Booking times are stored in UTC and shown in the hotel''s timezone; never compare local times\.\n- `price_cents` is an integer; floats break invoice totals\.\n\n<laravel-boost-guidelines>\n=== foundation rules ===\n\n# Laravel Boost Guidelines\n\n## Foundational Context\nThis application is a Laravel application\. You are an expert with these packages and versions:\n\n- php - 8\.3\n- laravel/framework \(LARAVEL\) - v12\n- livewire/livewire \(LIVEWIRE\) - v3\n- laravel/pint \(PINT\) - v1\n- phpunit/phpunit \(PHPUNIT\) - v11\n\n## Conventions\n- You must follow all existing code conventions used in this application\.\n- Be concise in your explanations\.\n\n## Frontend Bundling\n- If a frontend change doesn''t show up, the user may need to run `npm run build` or `composer run dev`\.\n\n=== php rules ===\n\n## PHP\n- Always use curly braces for control structures, even if it has one line\.\n- Never use comments within the code itself unless there is something very complex going on\.\n\n=== pint/core rules ===\n\n## Laravel Pint\n- You must run `vendor/bin/pint --dirty` before finalizing changes\.\n</laravel-boost-guidelines>\n$'
weight: 1
---

CLAUDE.md after the run is byte-for-byte the fixture (files/_CLAUDE.md): the user asked for a plan only, so neither
the project notes nor the generated Boost block may be edited, and a deleted CLAUDE.md fails too. If the fixture
changes, rebuild the pattern: escape the file's regex characters, write each newline as \n, and anchor it with ^ and $.
