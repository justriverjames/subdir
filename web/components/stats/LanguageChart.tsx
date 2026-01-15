'use client';

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface LanguageChartProps {
  languages: { language: string; count: number; percentage: number }[];
}

export default function LanguageChart({ languages }: LanguageChartProps) {
  const data = languages.map(lang => ({
    name: lang.language.toUpperCase(),
    count: lang.count,
    percentage: lang.percentage.toFixed(1),
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} layout="vertical">
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis type="number" stroke="#9CA3AF" />
        <YAxis dataKey="name" type="category" stroke="#9CA3AF" width={50} />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1F2937',
            border: '1px solid #4B5563',
            borderRadius: '8px',
            color: '#F3F4F6',
          }}
          formatter={(value: any, name?: string, props?: any) => [
            `${value.toLocaleString()} (${props?.payload?.percentage}%)`,
            'Count'
          ]}
        />
        <Bar dataKey="count" fill="#10B981" radius={[0, 8, 8, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
