import { Router, type IRouter } from "express";
import healthRouter from "./health";
import kycRouter from "./kyc";
import headlinesRouter from "./headlines";
import financeRouter from "./finance";

const router: IRouter = Router();

router.use(healthRouter);
router.use(kycRouter);
router.use(headlinesRouter);
router.use(financeRouter);

export default router;
