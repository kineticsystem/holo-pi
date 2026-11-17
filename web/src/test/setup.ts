// Before every test file: the DOM's matchers, e.g. toBeInTheDocument, and a clean page after each test.
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(cleanup);
