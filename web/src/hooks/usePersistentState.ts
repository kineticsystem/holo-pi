// A value the page remembers in the browser's storage, through the injected storage service: e.g. the upload
// form's last choice. A value it cannot read falls back.
import { useState } from 'react';
import { useServices } from '../services/ServicesContext';

export function usePersistentState(key: string, fallback: boolean): [boolean, (value: boolean) => void] {
  const { storage } = useServices();
  const [value, setValue] = useState<boolean>(() => {
    const saved = storage.getItem(key);
    return saved === 'true' ? true : saved === 'false' ? false : fallback;
  });
  function save(next: boolean) {
    setValue(next);
    storage.setItem(key, String(next));
  }
  return [value, save];
}
