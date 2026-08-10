import { useEffect, useState } from 'react';

import type {
  ChangeEvent,
  FormEvent,
} from 'react';

import {
  Link,
  Navigate,
} from 'react-router-dom';

import { authApi } from '../api/auth';

import {
  ApiRequestError,
  clearTokens,
  hasTokens,
} from '../api/client';

const maxDisplayNameLength = 40;
const maxNeighborhoodLength = 255;
const maxPhotoSizeBytes = 5 * 1024 * 1024;

const allowedPhotoTypes = [
  'image/jpeg',
  'image/png',
  'image/webp',
];

const mockAuthKey = 'mockAuthStatus'; // pragma: allowlist secret -- localStorage key name, not a credential
const mockProfileKey = 'mockUserProfile';

const isMockMode =
  import.meta.env.VITE_USE_MOCKS === 'true';

interface CachedProfile {
  userId?: string;
  displayName?: string;
  bio?: string;
  neighborhood?: string;
  photoUrl?: string | null;
  photoFileName?: string;
  profileSetupComplete?: boolean;
}

interface EditableProfileSnapshot {
  displayName: string;
  bio: string;
  neighborhood: string;
  photoUrl: string | null;
}

/**
 * Read the temporary frontend profile cache safely.
 *
 * The backend remains authoritative when the application is connected
 * to the real API. The cache supports mock mode and preserves the
 * profile-completion marker shared with ProfileSetupPage.
 */
function readCachedProfile(): CachedProfile | null {
  const savedProfile =
    localStorage.getItem(mockProfileKey);

  if (!savedProfile) {
    return null;
  }

  try {
    return JSON.parse(savedProfile) as CachedProfile;
  } catch {
    return null;
  }
}

/**
 * Notify the application that authentication has ended.
 */
function clearInvalidAuthentication() {
  clearTokens();
  localStorage.removeItem(mockAuthKey);

  window.dispatchEvent(
    new Event('auth-change'),
  );

  window.dispatchEvent(
    new Event('mock-auth-change'),
  );
}

/**
 * Issue #33 / User Story 6:
 * Member edits their own profile.
 *
 * Frontend behavior:
 * - Loads the authenticated member through GET /auth/me.
 * - Saves only through PUT /auth/me, so no other member ID can be targeted.
 * - Supports display name, bio, and neighborhood editing.
 * - Supports removal of an existing photo URL.
 * - Uploads a selected replacement photo through POST /auth/me/photo;
 *   invalid selections are rejected without changing the existing photo.
 * - Redirects unauthenticated users to Login.
 * - Silently performs no action when no saved fields changed.
 */
function EditProfilePage() {
  const hasApiSession = hasTokens();

  const hasMockSession =
    isMockMode &&
    localStorage.getItem(mockAuthKey) === 'logged-in';

  const isAuthenticated =
    hasApiSession || hasMockSession;

  const [currentUserId, setCurrentUserId] =
    useState<string | undefined>();

  const [displayName, setDisplayName] =
    useState('');

  const [bio, setBio] =
    useState('');

  const [neighborhood, setNeighborhood] =
    useState('');

  const [photoUrl, setPhotoUrl] =
    useState<string | null>(null);

  const [
    selectedPhotoFileName,
    setSelectedPhotoFileName,
  ] = useState('');
  const [selectedPhotoFile, setSelectedPhotoFile] =
    useState<File | null>(null);

  const [
    initialProfile,
    setInitialProfile,
  ] = useState<EditableProfileSnapshot | null>(
    null,
  );

  const [errorMessage, setErrorMessage] =
    useState('');

  const [successMessage, setSuccessMessage] =
    useState('');

  const [isLoading, setIsLoading] =
    useState(true);

  const [isSaving, setIsSaving] =
    useState(false);

  const [redirectToLogin, setRedirectToLogin] =
    useState(!isAuthenticated);

  /**
   * Load the current authenticated member.
   */
  useEffect(() => {
    let ignoreResult = false;

    async function loadProfile() {
      if (!isAuthenticated) {
        if (!isMockMode) {
          localStorage.removeItem(mockAuthKey);

          window.dispatchEvent(
            new Event('mock-auth-change'),
          );
        }

        if (!ignoreResult) {
          setRedirectToLogin(true);
          setIsLoading(false);
        }

        return;
      }

      const cachedProfile =
        readCachedProfile();

      /**
       * Compatibility path for a mock-only session without API tokens.
       */
      if (!hasApiSession) {
        const loadedProfile: EditableProfileSnapshot = {
          displayName:
            cachedProfile?.displayName ?? '',
          bio:
            cachedProfile?.bio ?? '',
          neighborhood:
            cachedProfile?.neighborhood ?? '',
          photoUrl:
            cachedProfile &&
            Object.prototype.hasOwnProperty.call(
              cachedProfile,
              'photoUrl',
            )
              ? cachedProfile.photoUrl ?? null
              : null,
        };

        if (!ignoreResult) {
          setCurrentUserId(cachedProfile?.userId);
          setDisplayName(loadedProfile.displayName);
          setBio(loadedProfile.bio);
          setNeighborhood(
            loadedProfile.neighborhood,
          );
          setPhotoUrl(loadedProfile.photoUrl);
          setInitialProfile(loadedProfile);
          setIsLoading(false);
        }

        return;
      }

      try {
        const currentUser =
          await authApi.me();

        if (ignoreResult) {
          return;
        }

        /**
         * Mock API handlers do not persist fixture changes between calls.
         * In mock mode only, a matching user cache may override fixture
         * values so a refresh still displays the saved mock profile.
         */
        const useMockCache =
          isMockMode &&
          cachedProfile?.userId === currentUser.id;

        const cachedPhotoUrl =
          useMockCache &&
          Object.prototype.hasOwnProperty.call(
            cachedProfile,
            'photoUrl',
          )
            ? cachedProfile?.photoUrl ?? null
            : currentUser.photo_url;

        const loadedProfile: EditableProfileSnapshot = {
          displayName: useMockCache
            ? cachedProfile?.displayName ??
              currentUser.full_name ??
              ''
            : currentUser.full_name ?? '',
          bio: useMockCache
            ? cachedProfile?.bio ??
              currentUser.bio ??
              ''
            : currentUser.bio ?? '',
          neighborhood: useMockCache
            ? cachedProfile?.neighborhood ??
              currentUser.neighborhood ??
              ''
            : currentUser.neighborhood ?? '',
          photoUrl: cachedPhotoUrl,
        };

        setCurrentUserId(currentUser.id);
        setDisplayName(loadedProfile.displayName);
        setBio(loadedProfile.bio);
        setNeighborhood(
          loadedProfile.neighborhood,
        );
        setPhotoUrl(loadedProfile.photoUrl);
        setInitialProfile(loadedProfile);
      } catch (error) {
        if (ignoreResult) {
          return;
        }

        if (
          error instanceof ApiRequestError &&
          error.status === 401
        ) {
          clearInvalidAuthentication();
          setRedirectToLogin(true);
          return;
        }

        if (
          error instanceof ApiRequestError &&
          error.status === 403
        ) {
          setErrorMessage(
            'You do not have permission to edit this profile.',
          );

          return;
        }

        setErrorMessage(
          error instanceof ApiRequestError
            ? error.detail
            : 'Unable to load your profile. Please try again.',
        );
      } finally {
        if (!ignoreResult) {
          setIsLoading(false);
        }
      }
    }

    void loadProfile();

    return () => {
      ignoreResult = true;
    };
  }, [hasApiSession, isAuthenticated]);

  /**
   * Validate a selected replacement photo.
   *
   * Invalid selection never changes photoUrl, so the currently saved
   * profile photo remains unchanged.
   */
  function handlePhotoChange(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    setErrorMessage('');
    setSuccessMessage('');

    const selectedFile =
      event.target.files?.[0];

    if (!selectedFile) {
      setSelectedPhotoFileName('');
      setSelectedPhotoFile(null);
      return;
    }

    if (
      !allowedPhotoTypes.includes(
        selectedFile.type,
      )
    ) {
      event.target.value = '';
      setSelectedPhotoFileName('');
      setSelectedPhotoFile(null);

      setErrorMessage(
        'Profile photo must be a JPG, PNG, or WebP image. Your existing photo was not changed.',
      );

      return;
    }

    if (
      selectedFile.size >
      maxPhotoSizeBytes
    ) {
      event.target.value = '';
      setSelectedPhotoFileName('');
      setSelectedPhotoFile(null);

      setErrorMessage(
        'Profile photo must be 5 MB or smaller. Your existing photo was not changed.',
      );

      return;
    }

    setSelectedPhotoFileName(
      selectedFile.name,
    );
    setSelectedPhotoFile(selectedFile);
  }

  /**
   * Remove the current saved photo URL.
   *
   * This is supported by PUT /auth/me using photo_url: null.
   */
  function handleRemovePhoto() {
    setErrorMessage('');
    setSuccessMessage('');
    setSelectedPhotoFileName('');
    setSelectedPhotoFile(null);
    setPhotoUrl(null);
  }

  /**
   * Save the current member's profile.
   */
  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (isSaving) {
      return;
    }

    setErrorMessage('');
    setSuccessMessage('');

    const normalizedDisplayName =
      displayName.trim();

    const normalizedBio =
      bio.trim();

    const normalizedNeighborhood =
      neighborhood.trim();

    if (!normalizedDisplayName) {
      setErrorMessage(
        'Display name is required.',
      );

      return;
    }

    if (
      normalizedDisplayName.length >
      maxDisplayNameLength
    ) {
      setErrorMessage(
        `Display name must be ${maxDisplayNameLength} characters or fewer.`,
      );

      return;
    }

    if (
      normalizedNeighborhood.length >
      maxNeighborhoodLength
    ) {
      setErrorMessage(
        `Neighborhood must be ${maxNeighborhoodLength} characters or fewer.`,
      );

      return;
    }

    if (!initialProfile) {
      setErrorMessage(
        'Your profile has not finished loading. Please try again.',
      );

      return;
    }

    const savedFieldsChanged =
      normalizedDisplayName !==
        initialProfile.displayName ||
      normalizedBio !==
        initialProfile.bio ||
      normalizedNeighborhood !==
        initialProfile.neighborhood ||
      photoUrl !== initialProfile.photoUrl;

    /**
     * Scenario 7: submitting unchanged saved fields is a silent no-op.
     */
    if (
      !savedFieldsChanged &&
      !selectedPhotoFileName
    ) {
      return;
    }

    setIsSaving(true);

    try {
      let savedUserId = currentUserId;

      let savedSnapshot: EditableProfileSnapshot = {
        displayName: normalizedDisplayName,
        bio: normalizedBio,
        neighborhood: normalizedNeighborhood,
        photoUrl,
      };

      if (hasApiSession) {
        let savedProfile =
          await authApi.updateMe({
            full_name:
              normalizedDisplayName,
            bio:
              normalizedBio || null,
            neighborhood:
              normalizedNeighborhood || null,
            photo_url:
              photoUrl,
          });

        if (selectedPhotoFile) {
          savedProfile =
            await authApi.uploadProfilePhoto(
              selectedPhotoFile,
            );
        }

        savedUserId = savedProfile.id;

        savedSnapshot = {
          displayName:
            savedProfile.full_name ??
            normalizedDisplayName,
          bio:
            savedProfile.bio ?? '',
          neighborhood:
            savedProfile.neighborhood ?? '',
          photoUrl:
            savedProfile.photo_url,
        };
      } else if (!hasMockSession) {
        setRedirectToLogin(true);
        return;
      }

      const cachedProfile: CachedProfile = {
        userId: savedUserId,
        displayName:
          savedSnapshot.displayName,
        bio:
          savedSnapshot.bio,
        neighborhood:
          savedSnapshot.neighborhood,
        photoUrl:
          savedSnapshot.photoUrl,
        photoFileName: '',
        profileSetupComplete: true,
      };

      if (hasApiSession) {
        try {
          localStorage.setItem(
            mockProfileKey,
            JSON.stringify(cachedProfile),
          );
        } catch {
          // The backend profile save remains authoritative.
        }
      } else {
        localStorage.setItem(
          mockProfileKey,
          JSON.stringify(cachedProfile),
        );
      }

      setCurrentUserId(savedUserId);
      setDisplayName(
        savedSnapshot.displayName,
      );
      setBio(savedSnapshot.bio);
      setNeighborhood(
        savedSnapshot.neighborhood,
      );
      setPhotoUrl(
        savedSnapshot.photoUrl,
      );
      setInitialProfile(savedSnapshot);
      setSelectedPhotoFileName('');
      setSelectedPhotoFile(null);

      setSuccessMessage(
        'Profile changes saved successfully.',
      );
    } catch (error) {
      if (
        error instanceof ApiRequestError &&
        error.status === 401
      ) {
        clearInvalidAuthentication();
        setRedirectToLogin(true);
        return;
      }

      if (
        error instanceof ApiRequestError &&
        error.status === 403
      ) {
        setErrorMessage(
          'You can only edit your own profile.',
        );

        return;
      }

      setErrorMessage(
        error instanceof ApiRequestError
          ? error.detail
          : error instanceof Error &&
              error.message.trim()
            ? error.message
            : 'Unable to save your profile. Please try again.',
      );
    } finally {
      setIsSaving(false);
    }
  }

  if (redirectToLogin) {
    return (
      <Navigate
        to="/login"
        replace
      />
    );
  }

  if (isLoading) {
    return (
      <section className="page-section">
        <div className="empty-state-card">
          <p className="eyebrow">
            Member Profile
          </p>

          <h1>
            Loading your profile...
          </h1>

          <p>
            Retrieving your current profile information.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <p className="eyebrow">
            Member Profile
          </p>

          <h1>
            Edit Profile
          </h1>

          <p className="page-description">
            Update your display name, short bio,
            neighborhood, and profile photo.
          </p>
        </div>

        <Link
          className="secondary-link header-action-link"
          to="/dashboard"
        >
          Back to Dashboard
        </Link>
      </div>

      <div className="profile-layout">
        <form
          className="profile-card"
          onSubmit={handleSubmit}
          noValidate
          aria-busy={isSaving}
        >
          <h2>
            Profile Details
          </h2>

          <label htmlFor="edit-profile-display-name">
            Display Name

            <input
              id="edit-profile-display-name"
              type="text"
              value={displayName}
              onChange={(event) =>
                setDisplayName(
                  event.target.value,
                )
              }
              maxLength={
                maxDisplayNameLength + 10
              }
              required
              disabled={isSaving}
            />
          </label>

          <p className="auth-helper-text">
            {displayName.trim().length}/
            {maxDisplayNameLength} characters
          </p>

          <label htmlFor="edit-profile-bio">
            Short Bio

            <textarea
              id="edit-profile-bio"
              value={bio}
              onChange={(event) =>
                setBio(event.target.value)
              }
              rows={4}
              placeholder="Tell neighbors a little about yourself."
              disabled={isSaving}
            />
          </label>

          <label htmlFor="edit-profile-neighborhood">
            Neighborhood or Location

            <input
              id="edit-profile-neighborhood"
              type="text"
              value={neighborhood}
              onChange={(event) =>
                setNeighborhood(
                  event.target.value,
                )
              }
              maxLength={maxNeighborhoodLength}
              placeholder="For example: Manoa, Kaimuki, or Honolulu"
              disabled={isSaving}
            />
          </label>

          <p className="auth-helper-text">
            Optional. This location may appear on
            your public member profile.
          </p>

          <label htmlFor="edit-profile-photo">
            Replacement Profile Photo

            <input
              id="edit-profile-photo"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={handlePhotoChange}
              disabled={isSaving}
            />
          </label>

          <p className="auth-helper-text">
            Accepted types: JPG, PNG, or WebP.
            Maximum size: 5 MB. The selected file
            is uploaded when you save your changes.
          </p>

          {photoUrl && (
            <button
              className="secondary-button"
              type="button"
              onClick={handleRemovePhoto}
              disabled={isSaving}
            >
              Remove Current Photo
            </button>
          )}

          <button
            className="primary-button"
            type="submit"
            disabled={isSaving}
          >
            {isSaving
              ? 'Saving Changes...'
              : 'Save Changes'}
          </button>

          <div aria-live="polite">
            {errorMessage && (
              <p
                className="form-error"
                role="alert"
              >
                {errorMessage}
              </p>
            )}

            {successMessage && (
              <p className="form-success">
                {successMessage}
              </p>
            )}
          </div>
        </form>

        <aside className="profile-card profile-preview-card">
          <h2>
            Profile Preview
          </h2>

          {selectedPhotoFileName ? (
            <div className="profile-avatar-preview">
              {selectedPhotoFileName
                .slice(0, 1)
                .toUpperCase()}
            </div>
          ) : photoUrl ? (
            <img
              className="public-profile-avatar"
              src={photoUrl}
              alt={`${displayName.trim() || 'Member'} profile`}
            />
          ) : (
            <div className="profile-avatar-preview">
              {'\u{1F464}'}
            </div>
          )}

          <h3>
            {displayName.trim() ||
              'Display Name Required'}
          </h3>

          <p>
            {bio.trim() ||
              'Your short bio will appear here.'}
          </p>

          <dl className="public-profile-detail-list">
            <div>
              <dt>
                Neighborhood
              </dt>

              <dd>
                {neighborhood.trim() ||
                  'Not provided'}
              </dd>
            </div>
          </dl>

          <p className="auth-helper-text">
            {selectedPhotoFileName
              ? `Selected replacement: ${selectedPhotoFileName}`
              : photoUrl
                ? 'Current saved profile photo'
                : 'No saved profile photo'}
          </p>
        </aside>
      </div>
    </section>
  );
}

export default EditProfilePage;
