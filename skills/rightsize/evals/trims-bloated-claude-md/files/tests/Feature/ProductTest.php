<?php

it('stores a product with its price in cents', function () {
    $this->postJson('/api/products', ['name' => 'Mug', 'amount' => 1250])
        ->assertCreated()
        ->assertJsonPath('data.amount', 1250);
});
