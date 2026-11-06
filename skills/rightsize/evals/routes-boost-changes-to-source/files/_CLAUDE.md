# Bookings

- Booking times are stored in UTC and shown in the hotel's timezone; never compare local times.
- `price_cents` is an integer; floats break invoice totals.

<laravel-boost-guidelines>
=== foundation rules ===

# Laravel Boost Guidelines

## Foundational Context
This application is a Laravel application. You are an expert with these packages and versions:

- php - 8.3
- laravel/framework (LARAVEL) - v12
- livewire/livewire (LIVEWIRE) - v3
- laravel/pint (PINT) - v1
- phpunit/phpunit (PHPUNIT) - v11

## Conventions
- You must follow all existing code conventions used in this application.
- Be concise in your explanations.

## Frontend Bundling
- If a frontend change doesn't show up, the user may need to run `npm run build` or `composer run dev`.

=== php rules ===

## PHP
- Always use curly braces for control structures, even if it has one line.
- Never use comments within the code itself unless there is something very complex going on.

=== pint/core rules ===

## Laravel Pint
- You must run `vendor/bin/pint --dirty` before finalizing changes.
</laravel-boost-guidelines>
