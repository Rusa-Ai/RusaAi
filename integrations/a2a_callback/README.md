## Callback polling

The authenticated polling endpoint returns at most 100 records per request. Use `?limit=25` to request a smaller page. When `next_cursor` is non-null, pass it unchanged as the `cursor` query parameter to fetch the next page. The cursor is opaque; do not construct or modify it. Reusing a `message_id` with exactly the same callback is acknowledged as a duplicate; reusing it for different content returns HTTP 409.

Callbacks require `Content-Type: application/json`, a positive `Content-Length` no larger than 1 MiB, and a valid signed timestamp/body. Duplicate JSON object keys and callbacks without a timezone-qualified ISO-8601 `created_at` are rejected.
