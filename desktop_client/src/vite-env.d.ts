/// <reference types="vite/client" />

interface Window {
  vtcm?: {
    selectFile: () => Promise<string | null>;
    backendUrl: () => Promise<string>;
  };
}

