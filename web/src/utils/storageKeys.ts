// Every key of the browser's storage that the page uses, in one place: changing one loses what users saved.
export const StorageKeys = {
  upload: {
    /** Whether an upload is shown at once, the first of several, "true" or "false": the form's last choice. */
    PLAY_AFTER_UPLOAD: 'holoPi.playAfterUpload',
  },
} as const;
