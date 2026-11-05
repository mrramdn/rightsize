# Rewrite patterns

Before/after pairs for the common cases. Adapt the wording to the repo and keep the user's voice; these show the
shape of the change, not text to paste.

- [Bare rule → outcome and reason](#bare-rule--outcome-and-reason)
- [Shouting → plain wording](#shouting--plain-wording)
- [Persona and scaffolding → nothing, or a concrete check](#persona-and-scaffolding--nothing-or-a-concrete-check)
- [Inline example → pointer to real code](#inline-example--pointer-to-real-code)
- [Embedded procedure → skill](#embedded-procedure--skill)
- [Derivable content → nothing](#derivable-content--nothing)
- [Duplicates → one home](#duplicates--one-home)
- [Conflict → one rule with a scope](#conflict--one-rule-with-a-scope)
- [Must-hold rule → guard plus one line](#must-hold-rule--guard-plus-one-line)
- [Vague skill description → what and when](#vague-skill-description--what-and-when)

## Bare rule → outcome and reason

A bare rule gets applied everywhere, including where it makes no sense. The reason lets Claude handle the cases the
rule didn't anticipate.

```text
Before: NEVER add comments to code.
After:  Match the comment density of the surrounding code; most files here have none.
```

```text
Before: DO NOT modify files in config/ without asking.
After:  config/ is shared with the infra team's deploy tooling, so ask before changing it.
```

If the reason is "because we said so", the rule may not be needed at all. Check whether the code already shows it.

## Shouting → plain wording

Capitals, IMPORTANT, CRITICAL and warning emoji made weaker models pay attention. Stronger models over-apply them.

```text
Before: IMPORTANT: ALWAYS use Form Requests for validation.
After:  Validate input with Form Requests (app/Http/Requests); controllers assume validated data.
```

## Persona and scaffolding → nothing, or a concrete check

```text
Before: You are an expert senior Laravel developer. Think step by step before answering.
After:  (delete)
```

```text
Before: Double-check your work before saying you are done.
After:  Before calling a change done, run `composer test`. It needs MySQL running (`docker compose up -d db`).
```

Keep a verification line only when it adds something Claude couldn't guess: the exact command, a prerequisite, a
slow suite to skip. "Run the tests" alone is something Claude already does.

## Inline example → pointer to real code

Pasted examples cost tokens every session, drift from the real code, and get copied too literally.

```text
Before: ## Example controller
        Use this as the template for every new controller:
        (25 lines of PHP)
After:  New controllers follow app/Http/Controllers/ProductController.php.
```

If no good example exists in the repo, that's worth telling the user; don't keep the pasted one by default.

## Embedded procedure → skill

A deploy runbook in CLAUDE.md is read on every turn, including all the turns that have nothing to do with deploying.
As a skill, only its description loads until someone deploys.

```text
Before: (CLAUDE.md) ## Deploying to the VPS
        1. SSH into the server ... 10. Bring the app back up
After:  (.claude/skills/deploy/SKILL.md)
        ---
        name: deploy
        description: Deploy Acme Shop to the production VPS (maintenance mode, pull, composer, migrations,
          assets, cache, queue restart). Use when asked to deploy, release or ship to production.
        ---
        (the steps, with the reason for any step that isn't obvious)
```

Nothing needs to stay in CLAUDE.md: the skill's description makes it discoverable. Keep one line only if Claude must
know something about deploys while doing other work (for example, "main deploys automatically on merge").

## Derivable content → nothing

```text
Before: ## Tech stack
        - Laravel 11
        - laravel/sanctum for API authentication
        - Pest for tests
After:  (delete; composer.json says this)
```

Keep the *why* if it's surprising: "Sanctum tokens, not sessions, because the Flutter app is the main client."

## Duplicates → one home

```text
Before: CLAUDE.md:                 IMPORTANT: ALWAYS write tests for every change.  (twice)
        .claude/rules/testing.md:  Always write tests for every change.
After:  .claude/rules/testing.md:  Add or update a Pest test with every behavior change.
        (removed from CLAUDE.md)
```

Pick the layer where the instruction applies. Testing rules live with testing; a rule about one directory lives in a
`paths:` rule for it.

## Conflict → one rule with a scope

```text
Before: CLAUDE.md:                NEVER add comments to code.
        .claude/rules/testing.md: Add comments to explain non-obvious test setup.
After:  CLAUDE.md:                Match the comment density of the surrounding code.
        .claude/rules/testing.md: In tests, a one-line comment on non-obvious setup is welcome.
```

When you can't tell which one the team means, ask. Don't resolve it silently.

## Must-hold rule → guard plus one line

```text
Before: NEVER run `php artisan migrate:fresh` against production. It drops every table.
After:  (hook) .claude/hooks/block-destructive.py refuses migrate:fresh, migrate:reset and db:wipe
        (CLAUDE.md) Destructive artisan commands are blocked by a hook; use the test database for resets.
```

The line in CLAUDE.md saves Claude a wasted turn and tells it what to do instead. See `enforcement.md`.

## Vague skill description → what and when

```text
Before: description: Review code
After:  description: Review a diff or pull request in this Laravel API for validation, authorization, N+1 queries,
          money handling and missing tests. Use when asked to review changes, a branch, a commit or a PR.
```

The description is the only part Claude sees before loading the skill, so it carries the trigger phrases.
