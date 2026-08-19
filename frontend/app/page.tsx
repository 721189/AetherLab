"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Bot,
  CloudSun,
  Leaf,
  Lock,
  MapPinned,
  LineChart,
} from "lucide-react";

const features = [
  {
    icon: CloudSun,
    title: "Live environmental monitoring",
    desc: "Air quality, weather and pollutant trends from OpenWeather & OpenAQ.",
  },
  {
    icon: Bot,
    title: "AI assistant",
    desc: "Chat with free Nemotron agents over OpenRouter — no paid tokens.",
  },
  {
    icon: LineChart,
    title: "Rich analytics",
    desc: "Interactive time-series charts for AQI, temperature and PM2.5.",
  },
  {
    icon: MapPinned,
    title: "Geographic insights",
    desc: "Environmental readings visualised by location.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-emerald-950/20 to-slate-950">
      <header className="mx-auto flex max-w-6xl items-center justify-between p-6">
        <div className="flex items-center gap-2 text-xl font-semibold text-white">
          <Leaf className="h-5 w-5" /> AetherLab
        </div>
        <nav className="flex items-center gap-4">
          <Link
            href="/login"
            className="rounded-md px-4 py-2 text-sm text-white/80 hover:bg-white/10"
          >
            Sign in
          </Link>
          <Link
            href="/register"
            className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-400"
          >
            Get started
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-16">
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center"
        >
          <h1 className="text-4xl font-bold tracking-tight text-white sm:text-6xl">
            Environmental intelligence,
            <span className="text-emerald-400"> powered by AI.</span>
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-white/70">
            Monitor air quality and weather, organise agents and projects, and
            ask questions with a free AI assistant — all in one platform.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/register"
              className="rounded-lg bg-emerald-500 px-6 py-3 text-white hover:bg-emerald-400"
            >
              Start monitoring free
            </Link>
            <Link
              href="/login"
              className="rounded-lg border border-white/20 px-6 py-3 text-white/90 hover:bg-white/10"
            >
              Sign in <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="mt-20 grid gap-6 sm:grid-cols-2 lg:grid-cols-4"
        >
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-2xl border border-white/10 bg-white/5 p-6"
            >
              <f.icon className="h-6 w-6 text-emerald-400" />
              <h3 className="mt-3 font-semibold text-white">{f.title}</h3>
              <p className="mt-2 text-sm text-white/60">{f.desc}</p>
            </div>
          ))}
        </motion.section>
      </main>

      <footer className="mx-auto max-w-6xl px-6 py-8 text-center text-sm text-white/50">
        AetherLab — environmental intelligence suite.
      </footer>
    </div>
  );
}