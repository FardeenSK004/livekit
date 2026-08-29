"""SQL Queries for PostgreSQL Full-Text Search and pgvector."""

import os

FTS_CONFIG = os.getenv("KB_FTS_CONFIG", "english")


def build_search_query(use_generated_column: bool = True) -> str:
    """Build strict FTS search query."""
    vector_expr = (
        "text_search"
        if use_generated_column
        else f"to_tsvector('{FTS_CONFIG}', coalesce(title, '') || ' ' || coalesce(content_in_text, ''))"
    )
    return f"""
        SELECT id, kb_id, title, content, source_type, page_meta, content_in_text, created_at,
               ts_rank({vector_expr}, websearch_to_tsquery('{FTS_CONFIG}', $2)) as similarity
        FROM kb_pages
        WHERE kb_id = ANY($1::text[])
          AND {vector_expr} @@ websearch_to_tsquery('{FTS_CONFIG}', $2)
          AND ($4::text[] IS NULL OR 
              (jsonb_typeof(page_meta->'tags_name') = 'array' AND page_meta->'tags_name' ?| $4::text[]) OR
              (jsonb_typeof(page_meta->'tags_name') = 'string' AND page_meta->>'tags_name' = ANY($4::text[]))
          )
        ORDER BY similarity DESC
        LIMIT $3
    """


def build_loose_search_query(use_generated_column: bool = True) -> str:
    """Loose (OR) FTS search matching ANY query term as fallback."""
    vector_expr = (
        "text_search"
        if use_generated_column
        else f"to_tsvector('{FTS_CONFIG}', coalesce(title, '') || ' ' || coalesce(content_in_text, ''))"
    )
    return f"""
        SELECT id, kb_id, title, content, source_type, page_meta, content_in_text, created_at,
               ts_rank({vector_expr}, plainto_tsquery('{FTS_CONFIG}', $2)) as similarity
        FROM kb_pages
        WHERE kb_id = ANY($1::text[])
          AND {vector_expr} @@ plainto_tsquery('{FTS_CONFIG}', $2)
          AND ($4::text[] IS NULL OR 
              (jsonb_typeof(page_meta->'tags_name') = 'array' AND page_meta->'tags_name' ?| $4::text[]) OR
              (jsonb_typeof(page_meta->'tags_name') = 'string' AND page_meta->>'tags_name' = ANY($4::text[]))
          )
        ORDER BY similarity DESC
        LIMIT $3
    """


def build_vector_search_query() -> str:
    """Semantic (pgvector) cosine distance query on embedding column."""
    return """
        SELECT id, kb_id, title, content, source_type, page_meta, content_in_text, created_at,
               1 - (embedding <=> $2::vector) as similarity
        FROM kb_pages
        WHERE kb_id = ANY($1::text[])
          AND embedding IS NOT NULL
          AND ($4::text[] IS NULL OR 
              (jsonb_typeof(page_meta->'tags_name') = 'array' AND page_meta->'tags_name' ?| $4::text[]) OR
              (jsonb_typeof(page_meta->'tags_name') = 'string' AND page_meta->>'tags_name' = ANY($4::text[]))
          )
        ORDER BY embedding <=> $2::vector
        LIMIT $3
    """


def build_tag_search_query() -> str:
    """Tag-only query without full text matching."""
    return """
        SELECT id, kb_id, title, content, source_type, page_meta, content_in_text, created_at,
               1.0 as similarity
        FROM kb_pages
        WHERE kb_id = ANY($1::text[])
          AND (
              (jsonb_typeof(page_meta->'tags_name') = 'array' AND page_meta->'tags_name' ?| $2::text[]) OR
              (jsonb_typeof(page_meta->'tags_name') = 'string' AND page_meta->>'tags_name' = ANY($2::text[]))
          )
        ORDER BY created_at DESC
        LIMIT $3
    """


def build_list_docs_query() -> str:
    """Distinct document titles available in KB."""
    return """
        SELECT DISTINCT ON (title) id, kb_id, title, content, source_type, page_meta, content_in_text, created_at
        FROM kb_pages
        WHERE kb_id = ANY($1::text[])
        ORDER BY title, created_at DESC
        LIMIT $2
    """
