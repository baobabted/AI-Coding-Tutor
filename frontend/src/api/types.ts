export interface User {
  id: string;
  email: string;
  username: string;
  programming_level: number;
  maths_level: number;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  username: string;
  password: string;
  programming_level?: number;
  maths_level?: number;
}

export interface ProfileUpdateData {
  username?: string;
  programming_level?: number;
  maths_level?: number;
}

export interface ChangePasswordData {
  current_password: string;
  new_password: string;
}

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  hint_level_used?: number;
  problem_difficulty?: number;
  maths_difficulty?: number;
  created_at?: string;
}

export interface ChatSession {
  id: string;
  preview: string;
  created_at: string;
}

export interface TokenUsage {
  date: string;
  input_tokens_used: number;
  output_tokens_used: number;
  daily_input_limit: number;
  daily_output_limit: number;
  usage_percentage: number;
}
