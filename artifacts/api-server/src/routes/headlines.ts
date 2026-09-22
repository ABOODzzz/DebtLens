import { Router, type IRouter } from "express";
import { desc } from "drizzle-orm";
import { db, headlinesTable } from "@workspace/db";
import { GetHeadlinesResponse } from "@workspace/api-zod";

const router: IRouter = Router();

router.get("/headlines", async (req, res) => {
  try {
    const rows = await db
      .select()
      .from(headlinesTable)
      .orderBy(desc(headlinesTable.publishedAt))
      .limit(30);

    const data = GetHeadlinesResponse.parse(
      rows.map((row) => ({
        id: row.id,
        text: row.text,
        source: row.source,
        publishedAt: row.publishedAt.toISOString(),
      })),
    );
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to load headlines");
    res.status(503).json({ error: "Headlines service unavailable" });
  }
});

export default router;
