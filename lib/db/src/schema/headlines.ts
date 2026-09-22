import { pgTable, serial, text, timestamp } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const headlinesTable = pgTable("headlines", {
  id: serial("id").primaryKey(),
  text: text("text").notNull(),
  source: text("source"),
  publishedAt: timestamp("published_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const insertHeadlineSchema = createInsertSchema(headlinesTable).omit({
  id: true,
});
export type InsertHeadline = z.infer<typeof insertHeadlineSchema>;
export type Headline = typeof headlinesTable.$inferSelect;
