import {
  integer,
  numeric,
  pgTable,
  serial,
  text,
  timestamp,
} from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const consolidationRequestsTable = pgTable("consolidation_requests", {
  id: serial("id").primaryKey(),
  uid: text("uid").notNull(),
  status: text("status").notNull().default("submitted"),
  institutionsIncluded: integer("institutions_included").notNull(),
  estimatedConsolidatedMonthlyPayment: numeric(
    "estimated_consolidated_monthly_payment",
    { precision: 12, scale: 2 },
  ).notNull(),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export const insertConsolidationRequestSchema = createInsertSchema(
  consolidationRequestsTable,
).omit({ id: true, createdAt: true });
export type InsertConsolidationRequest = z.infer<
  typeof insertConsolidationRequestSchema
>;
export type ConsolidationRequest =
  typeof consolidationRequestsTable.$inferSelect;
