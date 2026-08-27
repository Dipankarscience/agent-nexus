-- ===========================================
-- ADK Agent Hub - Database Schema
-- ===========================================

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) DEFAULT 'New Chat',
    agent_id VARCHAR(100) DEFAULT 'router',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    agent_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Dynamic agents table (for agent builder)
CREATE TABLE IF NOT EXISTS agents (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    system_prompt TEXT,
    tools_config JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    is_builtin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_agents_is_active ON agents(is_active);

-- Insert built-in agents
INSERT INTO agents (id, name, description, system_prompt, is_builtin, tools_config) VALUES
(
    'weather',
    'Weather Agent',
    'Provides current weather information for any city worldwide using Open-Meteo API.',
    'You are a helpful weather assistant. Use the get_weather tool to fetch current weather data for any location the user asks about. Always provide temperature, conditions, humidity, and wind information in a friendly format.',
    TRUE,
    '["get_weather"]'::jsonb
),
(
    'news',
    'News Agent',
    'Searches and summarizes the latest news on any topic using web search.',
    'You are a news assistant. Use the web_search tool to find the latest news articles on topics the user asks about. Summarize the key findings clearly and provide source references.',
    TRUE,
    '["web_search"]'::jsonb
),
(
    'planner',
    'Daily Planner Agent',
    'Helps plan your day with tasks, schedules, and weather-aware suggestions.',
    'You are a daily planning assistant. Help users organize their day, create task lists, set priorities, and make weather-aware suggestions. Use the get_weather tool when planning outdoor activities. Be proactive and suggest time blocks.',
    TRUE,
    '["get_weather", "web_search"]'::jsonb
)
ON CONFLICT (id) DO NOTHING;
