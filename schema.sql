-- Supabase Schema for Jobert AI Application Agent

-- Users table to store profile information
CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    notion_token TEXT, -- Encrypted
    gemini_api_key TEXT, -- Encrypted
    cv_url TEXT,
    notion_kb_page_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);

-- Applications table (for Phase 2+)
CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(telegram_id),
    job_url TEXT NOT NULL,
    company_name TEXT,
    role_title TEXT,
    notion_page_url TEXT,
    status TEXT DEFAULT 'Draft', -- Draft, Reviewed, Submitted
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
