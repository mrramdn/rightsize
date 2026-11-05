# Testing

- Always write tests for every change.
- Use Pest, not PHPUnit classes.
- Feature tests live in `tests/Feature` and call the API through `$this->postJson()`.
- Add comments to explain non-obvious test setup.
- Run `composer test` before you say you're done.
