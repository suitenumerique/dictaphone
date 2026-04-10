import { ApiError } from '../../../api/ApiError';
import { fetchApi } from '../../../api/fetchApi';
import { type ApiUser } from './ApiUser';
import {
  clearCachedUser,
  setCachedUser,
} from '@/services/storage';

/**
 * fetch the logged-in user from the api.
 *
 * If the user is not logged in, the api returns a 401 error.
 * Here our wrapper just returns false in that case, without triggering an error:
 * this is done to prevent unnecessary query retries with react query
 */
export const fetchUser = (): Promise<ApiUser | false> => {
  return new Promise((resolve, reject) => {
    fetchApi<ApiUser>('/users/me/')
      .then(user => {
        setCachedUser(user);
        resolve(user);
      })
      .catch(error => {
        // we assume that a 401 means the user is not logged in
        if (error instanceof ApiError && error.statusCode === 401) {
          clearCachedUser();
          // make sure to not resolve the promise while trying to silent login
          // so that consumers of fetchUser don't think the work already ended
          resolve(false);
        } else {
          reject(error);
        }
      });
  });
};
