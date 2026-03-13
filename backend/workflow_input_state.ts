/**
 * Input state for the writer Step Functions pipeline.
 *
 * Mirrors the initial fields of writer/workflow_state.py WorkflowState.
 * These are the fields the backend sets when starting a new execution.
 */
export interface WorkflowInputState {
  userId: string;
  customTopic?: string;
  followUpArticleId?: string;
  extraContent?: string;
}
