import { Link } from "wouter";
import { buttonVariants } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4 text-center">
      <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-6">
        <span className="text-3xl font-bold text-primary">404</span>
      </div>
      <h1 className="text-2xl font-bold text-primary mb-2">عذراً، الصفحة غير موجودة</h1>
      <p className="text-muted-foreground mb-8 max-w-md">
        يبدو أنك تبحث عن صفحة غير موجودة أو تم نقلها. يرجى التحقق من الرابط أو العودة إلى الصفحة الرئيسية.
      </p>
      <Link href="/" className={buttonVariants({ size: "lg", className: "bg-primary text-primary-foreground hover:bg-primary/90" })}>
        العودة للرئيسية
      </Link>
    </div>
  );
}
