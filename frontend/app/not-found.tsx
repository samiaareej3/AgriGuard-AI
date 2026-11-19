import Link from "next/link";
import { Leaf } from "lucide-react";

export default function NotFound() {
  return (
    <div className="grid min-h-screen place-items-center px-4 text-center">
      <div>
        <Leaf className="mx-auto size-10 text-primary" aria-hidden />
        <h1 className="mt-4 text-2xl font-semibold">Page not found</h1>
        <p className="mt-1 text-sm text-muted-foreground">The page you requested does not exist.</p>
        <Link href="/" className="mt-6 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">Back to overview</Link>
      </div>
    </div>
  );
}
