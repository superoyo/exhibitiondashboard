import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
  {
    // The legacy stack is not linted: the Python side is not JS, and the old
    // frontend/*.js is deleted page-by-page as React replaces it.
    ignores: [
      '**/dist/**',
      '**/node_modules/**',
      'frontend/**',
      'app/**',
      'migrations/**',
      'scripts/**',
      '_report_test/**',
    ],
  },

  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,

  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },

  // ---- Frontend -----------------------------------------------------------
  {
    files: ['apps/web/**/*.{ts,tsx}'],
    languageOptions: {
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },

  {
    // shadcn/ui primitives export their cva variant builders next to the
    // component by design, and the router/nav modules export route tables.
    // Fast-refresh granularity is not worth restructuring upstream files for.
    files: [
      'apps/web/src/components/ui/**/*.tsx',
      'apps/web/src/app/router.tsx',
      'apps/web/src/components/layout/NavBar.tsx',
      'apps/web/src/features/auth/components/UserAvatar.tsx',
    ],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },

  // ---- Backend ------------------------------------------------------------
  {
    files: ['apps/api/**/*.ts'],
    languageOptions: {
      globals: globals.node,
    },
    rules: {
      // Express error middleware legitimately takes 4 args with `next` unused.
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },

  // ---- Config files -------------------------------------------------------
  {
    files: ['**/*.config.{ts,js}', 'eslint.config.js'],
    ...tseslint.configs.disableTypeChecked,
  },

  prettier,
);
