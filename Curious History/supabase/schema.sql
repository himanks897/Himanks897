-- schema.sql — Supabase database schema for Curious History.
-- Run this in the Supabase SQL editor to set up all tables.

-- User profiles (extends Supabase auth.users)
CREATE TABLE IF NOT EXISTS user_profiles (
  id UUID REFERENCES auth.users PRIMARY KEY,
  display_name TEXT,
  streak_count INTEGER DEFAULT 0,
  last_visit_date DATE,
  total_searches INTEGER DEFAULT 0,
  reading_level TEXT DEFAULT 'student',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Search history
CREATE TABLE IF NOT EXISTS search_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users,
  topic TEXT NOT NULL,
  year INTEGER NOT NULL,
  country TEXT NOT NULL,
  era TEXT NOT NULL,
  searched_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id);
CREATE INDEX IF NOT EXISTS idx_search_history_date ON search_history(searched_at DESC);

-- Saved events
CREATE TABLE IF NOT EXISTS saved_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users,
  topic TEXT NOT NULL,
  year INTEGER NOT NULL,
  country TEXT NOT NULL,
  thumbnail_url TEXT,
  era TEXT DEFAULT 'ce',
  saved_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_saved_events_user ON saved_events(user_id);

-- Saved quotes
CREATE TABLE IF NOT EXISTS saved_quotes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users,
  quote_text TEXT NOT NULL,
  source_topic TEXT NOT NULL,
  source_year INTEGER,
  saved_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_saved_quotes_user ON saved_quotes(user_id);

-- Reactions
CREATE TABLE IF NOT EXISTS reactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_key TEXT NOT NULL,
  user_id UUID,
  reaction_type TEXT NOT NULL CHECK (reaction_type IN ('fascinating', 'shocking', 'inspiring', 'sad')),
  reacted_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(event_key, user_id)
);
CREATE INDEX IF NOT EXISTS idx_reactions_event ON reactions(event_key);

-- User stats (milestones)
CREATE TABLE IF NOT EXISTS user_stats (
  user_id UUID REFERENCES auth.users PRIMARY KEY,
  milestones_reached TEXT[] DEFAULT '{}',
  streak_best INTEGER DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security (optional but recommended)
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE search_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_stats ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can read own profile" ON user_profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON user_profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can read own searches" ON search_history FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own searches" ON search_history FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can read own saves" ON saved_events FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own saves" ON saved_events FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own saves" ON saved_events FOR DELETE USING (auth.uid() = user_id);
CREATE POLICY "Users can read own quotes" ON saved_quotes FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own quotes" ON saved_quotes FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Anyone can read reactions" ON reactions FOR SELECT USING (true);
CREATE POLICY "Anyone can insert reactions" ON reactions FOR INSERT WITH CHECK (true);
