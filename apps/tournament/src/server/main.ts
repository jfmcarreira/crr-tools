import { createApp } from './app.js';

const port = 8080;
const host = process.env.HOST ?? '0.0.0.0';

async function start(): Promise<void> {
  const app = await createApp({ logger: true });
  try {
    await app.listen({ host, port });
  } catch (error) {
    app.log.error(error);
    process.exitCode = 1;
    await app.close();
  }
}

void start();
