"use client";

import { use } from "react";
import { EditorShell } from "@/components/editor/editor-shell";

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <EditorShell key={id} pid={id} />;
}
