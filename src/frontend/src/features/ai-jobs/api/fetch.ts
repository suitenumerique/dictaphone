import { fetchApi } from '@/api/fetchApi'
import { useMutation, useQuery } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys'
import { ApiAiJob, ApiOpenInDocsResponse, WhisperXResponse } from '@/features/ai-jobs/api/types.ts'

export const getTranscript = async (
  aiJob: ApiAiJob | null
): Promise<WhisperXResponse> => {
  if (!aiJob || !aiJob.id) {
    throw new Error('No aiJob provided')
  }
  return fetchApi<WhisperXResponse>(`/ai-jobs/${aiJob.id}/transcript/`, {
    method: 'GET',
  })
}

export const getSummary = async (aiJob: ApiAiJob | null): Promise<string> => {
  if (!aiJob || !aiJob.id) {
    throw new Error('No aiJob provided')
  }
  return fetchApi<string>(`/ai-jobs/${aiJob.id}/summary/`, {
    method: 'GET',
  })
}

export const openInDocs = async (aiJob: ApiAiJob | null): Promise<ApiOpenInDocsResponse> => {
  if (!aiJob || !aiJob.id) {
    throw new Error('No aiJob provided')
  }
  return fetchApi<ApiOpenInDocsResponse>(`/ai-jobs/${aiJob.id}/open-in-docs/`, {
    method: 'POST',
  })
}

export const useTranscript = (params: Parameters<typeof getTranscript>[0]) => {
  return useQuery({
    queryKey: [keys.aiJobs, params?.id, params],
    queryFn: () => getTranscript(params),
    enabled: params?.status === 'success' && Boolean(params?.id),
  })
}

export const useSummary = (params: Parameters<typeof getSummary>[0]) => {
  return useQuery({
    queryKey: [keys.aiJobs, params?.id, params],
    queryFn: () => getSummary(params),
    enabled: params?.status === 'success' && Boolean(params?.id),
  })
}

export const useOpenInDocsMutation = () => {
  return useMutation({
    mutationFn: openInDocs,
  })
}
