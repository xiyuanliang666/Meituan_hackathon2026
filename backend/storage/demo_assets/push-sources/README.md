# Push source demo assets

Reserved folder for the "爆款来源" source-post demo materials.

Recommended future structure:

- `{push_id}__source-1.png`
- `{push_id}__source-2.png`
- `{push_id}__source-3.png`
- `{push_id}__sources.json`

Each source item should include:

- `image`: cover image filename.
- `title`: original post title, usually the first line of the post body.
- `platform`: source platform, such as `小红书`.
- `url`: original post URL.
- `published_at`: absolute publish date in `YYYY-MM-DD`.
- `relative_time`: display text such as `3天前`.
- `metrics.likes`: like count.
- `metrics.favorites`: favorite/save count.
- `metrics.comments`: comment count.
- `metrics.growth_3d`: favorite-count growth over 3 days as a percentage number, for example `15`.
- `status.key`: machine key, for example `hot`.
- `status.label`: display label, for example `爆款`.

Use `manifest.example.json` as the exact shape.
