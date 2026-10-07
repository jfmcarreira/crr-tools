import type { ServerResponse } from 'node:http';

/** Keeps SSE connections as notification-only streams, never state replicas. */
export class StateChangeEvents {
  private readonly clients = new Set<ServerResponse>();
  private readonly heartbeat: NodeJS.Timeout;

  public constructor(heartbeatMs = 25_000) {
    this.heartbeat = setInterval(() => this.writeToAll(': heartbeat\n\n'), heartbeatMs);
    this.heartbeat.unref();
  }

  public add(response: ServerResponse): void {
    this.clients.add(response);
    response.write('retry: 3000\n\n');
  }

  public remove(response: ServerResponse): void {
    this.clients.delete(response);
  }

  public broadcastStateChanged(): void {
    this.writeToAll('event: state-changed\ndata: {"type":"state-changed"}\n\n');
  }

  public close(): void {
    clearInterval(this.heartbeat);
    for (const client of this.clients) {
      client.end();
    }
    this.clients.clear();
  }

  private writeToAll(message: string): void {
    for (const client of this.clients) {
      if (client.destroyed) {
        this.clients.delete(client);
        continue;
      }
      client.write(message);
    }
  }
}
