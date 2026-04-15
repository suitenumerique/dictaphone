import { fetchApi } from '@/api/fetchApi';
import {
  keepPreviousData,
  useInfiniteQuery,
  useQuery,
} from '@tanstack/react-query';
import { keys } from '@/api/queryKeys';
import {
  ApiFileItem,
  ApiFileType,
  ApiFileUploadState,
} from '@/features/files/api/types.ts';
import { shouldRefetchMainAiJobs } from '@/features/ai-jobs/utils/getMainAiJobs.ts';
import { useUser } from '@/features/auth/api/useUser';

const REFRESH_AI_JOBS_INTERVAL_MS = 10_000;

export type ListFilesResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: ApiFileItem[];
};

type ListFilesFilters = {
  is_creator_me?: boolean;
  type?: ApiFileType;
  upload_state?: ApiFileUploadState;
  is_deleted?: boolean;
};

export type ListFilesParams = {
  filters?: ListFilesFilters;
  pagination: {
    page: number;
    pageSize: number;
  };
};

type ListFilesInfiniteParams = {
  filters?: ListFilesFilters;
  pageSize?: number;
};

export const listMyFiles = async ({
  filters = {},
  pagination: { page, pageSize },
}: ListFilesParams): Promise<ListFilesResponse> => {
  const query = new URLSearchParams();
  query.append('page', page.toString());
  query.append('page_size', pageSize.toString());
  if (filters?.is_creator_me ?? true) {
    query.append('is_creator_me', 'true');
  }
  if (filters?.type) {
    query.append('type', filters.type);
  }
  if (filters?.upload_state) {
    query.append('upload_state', filters.upload_state);
  }
  if (typeof filters?.is_deleted === 'boolean') {
    query.append('is_deleted', filters.is_deleted ? 'true' : 'false');
  }

  return fetchApi<ListFilesResponse>(`/files?${query.toString()}`, {
    method: 'GET',
  });
};

const getPageFromUrl = (nextUrl: string | null) => {
  if (!nextUrl) {
    return undefined;
  }

  const searchParams = new URLSearchParams(nextUrl)
  const page = Number.parseInt(searchParams.get("page") ?? "0", 10)
  return Number.isFinite(page) ? page : undefined
};

export const useListMyFiles = (params: Parameters<typeof listMyFiles>[0]) => {
  const { isLoggedIn } = useUser();
  return useQuery({
    queryKey: [keys.files, params],
    queryFn: () => listMyFiles(params),
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: query => {
      const files = query.state.data?.results;
      if (!files) {
        return false;
      }
      return files.some(file => shouldRefetchMainAiJobs(file.ai_jobs))
        ? REFRESH_AI_JOBS_INTERVAL_MS
        : false;
    },
    placeholderData: keepPreviousData,
    enabled: isLoggedIn,
  });
};

export const useListMyFilesInfinite = ({
  filters,
  pageSize = 100,
}: ListFilesInfiniteParams) => {
  const { isLoggedIn } = useUser();

  return useInfiniteQuery({
    queryKey: [keys.files, 'infinite', { filters, pageSize }],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      listMyFiles({
        filters,
        pagination: {
          page: pageParam,
          pageSize,
        },
      }),
    getNextPageParam: lastPage => getPageFromUrl(lastPage.next),
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: query => {
      const files = query.state.data?.pages.flatMap(page => page.results);
      if (!files) {
        return false;
      }

      return files.some(file => shouldRefetchMainAiJobs(file.ai_jobs))
        ? REFRESH_AI_JOBS_INTERVAL_MS
        : false;
    },
    enabled: isLoggedIn,
  });
};
