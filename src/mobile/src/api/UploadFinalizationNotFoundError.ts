import { ApiError, type ApiErrorRequest } from './ApiError'

// Only a 404 from POST upload-ended may reset an upload attempt. A 404 from
// creation or the GET used to reconcile a 400 must retain its normal handling.
export class UploadFinalizationNotFoundError extends ApiError {
  constructor(body: unknown, request?: ApiErrorRequest) {
    super(404, body, null, request)
  }
}
