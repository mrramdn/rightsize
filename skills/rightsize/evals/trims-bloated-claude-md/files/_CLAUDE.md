# Acme Shop API

You are an expert senior Laravel developer with 15 years of experience. Think step by step before answering.

## Project overview

Acme Shop is the backend for our online store. It serves a JSON API to the Flutter app and the admin panel.

## Tech stack

- Laravel 11
- PHP 8.3
- laravel/sanctum for API authentication
- spatie/laravel-permission for roles
- Pest for tests
- Vite for frontend assets
- MySQL 8

## Directory structure

```
app/
├── Http/
│   ├── Controllers/
│   └── Requests/
├── Models/
├── Services/
routes/
├── api.php
└── web.php
tests/
├── Feature/
└── Unit/
```

## Rules

- IMPORTANT: ALWAYS write tests for every change.
- NEVER add comments to code.
- Use camelCase for variables and PascalCase for classes.
- ALWAYS use Form Requests for validation.
- DO NOT modify files in config/ without asking.
- Prices are stored as integers in cents in the `amount` column; never use floats for money, because rounding errors break invoice totals.
- NEVER run `php artisan migrate:fresh` against production. It drops every table.
- The .env file contains secrets. DO NOT read it or print it.
- Double-check your work before saying you are done.
- Be thorough and careful.
- Follow PSR-12.
- IMPORTANT: ALWAYS write tests for every change.

## Example controller

Use this as the template for every new controller:

```php
<?php

namespace App\Http\Controllers;

use App\Http\Requests\StoreProductRequest;
use App\Models\Product;
use Illuminate\Http\JsonResponse;

class ProductController extends Controller
{
    public function index(): JsonResponse
    {
        return response()->json(Product::query()->paginate(20));
    }

    public function store(StoreProductRequest $request): JsonResponse
    {
        $product = Product::create($request->validated());

        return response()->json($product, 201);
    }
}
```

## Code review checklist

When reviewing code, check:

1. Naming is clear
2. Validation uses Form Requests
3. No N+1 queries (use eager loading)
4. Authorization is handled by policies
5. Money is stored in cents
6. Tests cover the happy path
7. Tests cover failure cases
8. No secrets in code
9. API resources are used for responses
10. Migrations are reversible
11. Jobs are idempotent
12. Logs don't contain personal data

## Deploying to the VPS

1. SSH into the server: `ssh deploy@203.0.113.10`
2. Go to the app directory: `cd /var/www/acme-shop`
3. Put the app in maintenance mode: `php artisan down`
4. Pull the latest code: `git pull origin main`
5. Install dependencies: `composer install --no-dev --optimize-autoloader`
6. Run migrations: `php artisan migrate --force`
7. Build assets: `npm ci && npm run build`
8. Clear and rebuild caches: `php artisan optimize`
9. Restart the queue workers: `php artisan queue:restart`
10. Bring the app back up: `php artisan up`

## Useful commands

- `composer test` runs the test suite
- `composer run analyse` runs PHPStan
- `npm run lint` lints the frontend
- `npm run dev` starts Vite

## Architecture

See `docs/architecture.md` for the full architecture and `app/Services/PaymentService.php` for the payment flow.

## Notes

- 2026-03-02: fixed the cart total bug, check cart totals after changes
- 2026-03-09: switched the queue driver to redis
- 2026-04-11: added the refunds endpoint
