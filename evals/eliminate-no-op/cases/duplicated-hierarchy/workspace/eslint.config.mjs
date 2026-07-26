import tseslint from 'typescript-eslint';

export default tseslint.config({
  files: ['packages/*/src/**/*.{ts,tsx}'],
  rules: { '@typescript-eslint/no-explicit-any': 'error' },
});
