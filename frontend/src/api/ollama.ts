import { apiGet } from "./client";

export interface OllamaStatus {
  online: boolean;
  models: {
    name: string;
  }[];
}

export function getOllamaStatus() {
  return apiGet<OllamaStatus>("/ollama/status");
}