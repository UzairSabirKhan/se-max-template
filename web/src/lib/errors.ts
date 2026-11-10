import type { ApiErrorBody, Issue } from "../types/contracts";

export class ApiError extends Error {
  status: number;
  code: string;
  issues: Issue[];
  constructor(status: number, body: ApiErrorBody) {
    super(body.message || friendly(body.error));
    this.status = status;
    this.code = body.error;
    this.issues = body.issues ?? [];
  }
}

export function friendly(code: string) {
  switch (code) {
    case "version_conflict":
      return "This flow was changed somewhere else.";
    case "invalid_flow":
      return "Some steps need fixing.";
    case "already_running":
      return "This flow is already running.";
    case "rate_limited":
      return "Too many requests. Wait a moment and try again.";
    default:
      return "Something went wrong. Try again.";
  }
}

