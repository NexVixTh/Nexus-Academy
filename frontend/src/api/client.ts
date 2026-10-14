import type {
  AskResponse,
  DocumentAssetsResponse,
  DocumentConceptsResponse,
  DocumentListResponse,
  DocumentSearchResponse,
  HealthResponse,
  IngestionResponse,
  LearnerDocumentProgressResponse,
  LearnerGamificationResponse,
  LearnerProfile,
  LearnerProgressResponse,
  ModelStatusResponse,
  QuizResponse,
  QuizSubmissionRequest,
  QuizSubmissionResponse,
} from "../types/api";

const BASE_URL = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    message: string,
    public detail?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type") &&
    options.method &&
    options.method !== "GET"
  ) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch (err) {
    throw new ApiError(
      0,
      "NetworkError",
      "Unable to reach NEXUS ACADEMY backend. Please verify the service is running."
    );
  }

  if (!response.ok) {
    let errorDetail = "";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") {
        errorDetail = data.detail;
      } else if (Array.isArray(data.detail)) {
        errorDetail = data.detail.map((d: { msg?: string }) => d.msg || "").join("; ");
      } else {
        errorDetail = JSON.stringify(data);
      }
    } catch {
      errorDetail = await response.text();
    }

    const message =
      errorDetail || `Request failed with status ${response.status} (${response.statusText})`;
    throw new ApiError(response.status, response.statusText, message, errorDetail);
  }

  return response.json() as Promise<T>;
}

export const api = {
  async getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  async getModelsStatus(): Promise<ModelStatusResponse> {
    return request<ModelStatusResponse>("/models/status");
  },

  async listDocuments(): Promise<DocumentListResponse> {
    return request<DocumentListResponse>("/documents");
  },

  async uploadDocument(file: File): Promise<IngestionResponse> {
    const formData = new FormData();
    formData.append("file", file, file.name);

    return request<IngestionResponse>("/documents", {
      method: "POST",
      body: formData,
    });
  },

  async getDocumentConcepts(documentId: string): Promise<DocumentConceptsResponse> {
    return request<DocumentConceptsResponse>(
      `/documents/${encodeURIComponent(documentId)}/concepts`
    );
  },

  async searchDocument(
    documentId: string,
    query: string
  ): Promise<DocumentSearchResponse> {
    return request<DocumentSearchResponse>(
      `/documents/${encodeURIComponent(documentId)}/search?query=${encodeURIComponent(query)}`
    );
  },

  async getDocumentAssets(documentId: string): Promise<DocumentAssetsResponse> {
    return request<DocumentAssetsResponse>(
      `/documents/${encodeURIComponent(documentId)}/assets`
    );
  },

  async askDocument(documentId: string, question: string): Promise<AskResponse> {
    return request<AskResponse>(
      `/documents/${encodeURIComponent(documentId)}/ask`,
      {
        method: "POST",
        body: JSON.stringify({ question }),
      }
    );
  },

  async createLearner(): Promise<LearnerProfile> {
    return request<LearnerProfile>("/learners", {
      method: "POST",
    });
  },

  async getLearnerProgress(learnerId: string): Promise<LearnerProgressResponse> {
    return request<LearnerProgressResponse>(
      `/learners/${encodeURIComponent(learnerId)}/progress`
    );
  },

  async getLearnerGamification(
    learnerId: string
  ): Promise<LearnerGamificationResponse> {
    return request<LearnerGamificationResponse>(
      `/learners/${encodeURIComponent(learnerId)}/gamification`
    );
  },

  async getLearnerDocumentProgress(
    learnerId: string,
    documentId: string
  ): Promise<LearnerDocumentProgressResponse> {
    return request<LearnerDocumentProgressResponse>(
      `/learners/${encodeURIComponent(learnerId)}/documents/${encodeURIComponent(
        documentId
      )}/progress`
    );
  },

  async generateQuiz(
    documentId: string,
    questionCount: number = 5,
    learnerId?: string | null
  ): Promise<QuizResponse> {
    return request<QuizResponse>(
      `/documents/${encodeURIComponent(documentId)}/quiz`,
      {
        method: "POST",
        body: JSON.stringify({
          question_count: questionCount,
          ...(learnerId ? { learner_id: learnerId } : {}),
        }),
      }
    );
  },

  async generateAdaptiveQuiz(
    learnerId: string,
    documentId: string,
    questionCount: number = 5
  ): Promise<QuizResponse> {
    return request<QuizResponse>(
      `/learners/${encodeURIComponent(learnerId)}/documents/${encodeURIComponent(
        documentId
      )}/quiz`,
      {
        method: "POST",
        body: JSON.stringify({
          question_count: questionCount,
        }),
      }
    );
  },

  async submitQuiz(
    documentId: string,
    submission: QuizSubmissionRequest
  ): Promise<QuizSubmissionResponse> {
    return request<QuizSubmissionResponse>(
      `/documents/${encodeURIComponent(documentId)}/quiz/submit`,
      {
        method: "POST",
        body: JSON.stringify(submission),
      }
    );
  },
};
