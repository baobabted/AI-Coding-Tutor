export interface User {
  id: string;
  email: string;
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
  password: string;
  programming_level?: number;
  maths_level?: number;
}

export interface UserAssessment {
  programming_level: number;
  maths_level: number;
}
