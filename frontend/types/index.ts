// TypeScript mirrors of the backend Pydantic schemas.

export interface Token {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface User {
  id: number;
  email: string;
  is_verified: boolean;
}

export interface UserRegisterResponse {
  user: User;
  verification_token: string;
  message: string;
}

export interface VerificationResponse {
  message: string;
  verification_token?: string;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  owner_id: number;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export type ProjectInput = Pick<Project, "name"> & {
  description?: string | null;
};

export type AgentStatus = "active" | "inactive" | "paused" | "archived";
export const AGENT_STATUSES: AgentStatus[] = [
  "active",
  "inactive",
  "paused",
  "archived",
];

export interface Agent {
  id: number;
  project_id: number;
  name: string;
  description: string | null;
  model: string;
  system_prompt: string | null;
  temperature: number;
  max_tokens: number | null;
  configuration: Record<string, unknown> | null;
  status: AgentStatus;
  is_public: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentCreateInput {
  name: string;
  description?: string | null;
  model?: string;
  system_prompt?: string | null;
  temperature?: number;
  max_tokens?: number | null;
  configuration?: Record<string, unknown>;
  status?: AgentStatus;
}

export type AgentUpdateInput = Partial<AgentCreateInput> & { is_public?: boolean };

export interface Conversation {
  id: number;
  project_id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export type ConversationCreate = Pick<Conversation, "title">;

export type MessageRole = "user" | "assistant";

export interface Message {
  id: number;
  conversation_id: number;
  role: MessageRole;
  content: string;
  created_at: string;
}

// Response shape returned by POST .../messages
export interface MessageExchange {
  user_message: Message;
  assistant_message: Message;
}

export interface EnvironmentalSummary {
  source: string;
  temperature: number | null;
  aqi: number | null;
  pm25: number | null;
  recorded_at: string;
}

export interface EnvironmentalReading {
  id: number;
  location_name: string;
  lat: number;
  lon: number;
  source: string;
  temperature: number | null;
  feels_like: number | null;
  humidity: number | null;
  wind_speed: number | null;
  wind_direction: number | null;
  pressure: number | null;
  uv_index: number | null;
  weather_description: string | null;
  aqi: number | null;
  pm25: number | null;
  pm10: number | null;
  no2: number | null;
  o3: number | null;
  co: number | null;
  so2: number | null;
  recorded_at: string;
  created_at: string;
}