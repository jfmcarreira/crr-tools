import { fileURLToPath, URL } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
// PWA plugin removed for CI parity

const brandRoot = fileURLToPath(new URL('../../../packages/crr-brand', import.meta.url));

function deploymentBase(base: string | undefined): string {
  const value = base ?? '/';
  if (!value.startsWith('/')) {
    throw new Error('VITE_BASE_PATH tem de começar por "/".');
  }
  return value.endsWith('/') ? value : `${value}/`;
}

export default defineConfig(({ mode }) => {
  const base = deploymentBase(loadEnv(mode, fileURLToPath(new URL('..', import.meta.url)), '').VITE_BASE_PATH);

  return {
    base,
    publicDir: `${brandRoot}/assets`,
    plugins: [vue()],
    server: {
      fs: {
        allow: [fileURLToPath(new URL('.', import.meta.url)), brandRoot],
      },
      proxy: {
        [`${base}api`]: {
          target: 'http://localhost:8080',
          rewrite: (path) => path.replace(`${base}api`, '/api'),
        },
      },
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        '@crr-brand': brandRoot,
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
    },
  };
});
