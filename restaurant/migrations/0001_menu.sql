-- Menu: categories, dishes, dietary tags.

CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE dishes (
    id INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    image_url TEXT,
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
    is_archived INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0, 1)),
    prep_minutes INTEGER NOT NULL DEFAULT 10 CHECK (prep_minutes >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX idx_dishes_category_available ON dishes (category_id, is_available);
CREATE INDEX idx_dishes_slug ON dishes (slug);

CREATE TABLE dietary_tags (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL
);

CREATE TABLE dish_tags (
    dish_id INTEGER NOT NULL REFERENCES dishes(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES dietary_tags(id) ON DELETE RESTRICT,
    PRIMARY KEY (dish_id, tag_id)
);
