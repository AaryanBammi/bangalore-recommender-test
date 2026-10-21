// Mirrors backend/models.py.

export type Budget = "low" | "medium" | "high";

export interface Options {
  locations: string[];
  cuisines: string[];
}

export interface RecommendationRequest {
  location: string;
  budget: Budget;
  cuisines: string[];
  min_rating: number;
  preference: string;
}

export interface RecommendationItem {
  rank: number;
  name: string;
  cuisines: string[];
  rating: number | null;
  cost_for_two: number | null;
  location: string;
  explanation: string | null;
}

export interface RecommendationResponse {
  recommendations: RecommendationItem[];
  summary: string | null;
  candidates_considered: number;
  notes: string[];
  degraded: boolean;
}
