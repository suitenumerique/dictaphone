import { fetchApi } from '@/api/fetchApi'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { keys } from '@/api/queryKeys'
import {
  ApiAiJob,
  ApiOpenInDocsResponse,
  TTranscriptionLanguage,
  WhisperXResponse,
} from '@/features/ai-jobs/api/types.ts'
import { MOCK_DATA } from '@/api/constants'
import { mockedTranscript } from '@/features/ai-jobs/api/mockData'

export const getTranscript = async (
  aiJob: Pick<ApiAiJob, 'id'> | null
): Promise<WhisperXResponse> => {
  if (MOCK_DATA) {
    return mockedTranscript
  }
  if (!aiJob || !aiJob.id) {
    throw new Error('No aiJob provided')
  }
  return fetchApi<WhisperXResponse>(`/ai-jobs/${aiJob.id}/transcript/`, {
    method: 'GET',
    rateLimitScope: 'aiResult',
  })
}

export const getSummary = async (
  aiJob: Pick<ApiAiJob, 'id'> | null
): Promise<string> => {
  if (!aiJob || !aiJob.id) {
    throw new Error('No aiJob provided')
  }
  return fetchApi<string>(`/ai-jobs/${aiJob.id}/summary/`, {
    method: 'GET',
    rateLimitScope: 'aiResult',
  })
}

export const openInDocs = async (
  aiJob: ApiAiJob | null
): Promise<ApiOpenInDocsResponse> => {
  if (!aiJob || !aiJob.id) {
    throw new Error('No aiJob provided')
  }
  return fetchApi<ApiOpenInDocsResponse>(`/ai-jobs/${aiJob.id}/open-in-docs/`, {
    method: 'POST',
  })
}

export const createInDocs = async (
  aiJob: ApiAiJob | null
): Promise<ApiOpenInDocsResponse> => {
  if (!aiJob || !aiJob.id) {
    throw new Error('No aiJob provided')
  }
  return fetchApi<ApiOpenInDocsResponse>(
    `/ai-jobs/${aiJob.id}/create-in-docs/`,
    {
      method: 'POST',
      rateLimitScope: 'docsCreate',
    }
  )
}

export const retryWithLanguage = async ({
  id,
  language,
}: {
  id: string
  language: TTranscriptionLanguage
}): Promise<ApiAiJob> => {
  if (!id) {
    throw new Error('Missing aiJob id')
  }

  return fetchApi<ApiAiJob>(`/ai-jobs/${id}/retry/`, {
    method: 'POST',
    body: JSON.stringify({
      language,
    }),
    rateLimitScope: 'transcriptionRetry',
  })
}

export const useTranscript = (params: ApiAiJob | null) => {
  const id = params?.id ?? null
  return useQuery({
    queryKey: [keys.aiJobs, id, 'transcript'],
    queryFn: () => getTranscript({ id }),
    enabled: params?.status === 'success' && Boolean(params?.id),
    // Results of a given job never change, and they count toward a server rate limit.
    staleTime: Infinity,
  })
}

export const useSummary = (params: ApiAiJob | null) => {
  const id = params?.id ?? null
  return useQuery({
    queryKey: [keys.aiJobs, id, 'summary'],
    queryFn: () => getSummary({ id }),
    enabled: params?.status === 'success' && Boolean(params?.id),
    // Results of a given job never change, and they count toward a server rate limit.
    staleTime: Infinity,
  })
}

export const useOpenInDocsMutation = () => {
  return useMutation({
    mutationFn: openInDocs,
  })
}

export const useCreateInDocsMutation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createInDocs,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [keys.files],
      })
    },
  })
}

export const useRetryWithLanguageMutation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: retryWithLanguage,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [keys.aiJobs],
      })
      queryClient.invalidateQueries({
        queryKey: [keys.files],
      })
    },
  })
}
