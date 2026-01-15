'use client';

import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface AgeChartProps {
  distribution: { year: string; count: number }[];
}

export default function AgeChart({ distribution }: AgeChartProps) {
  const data = distribution.map(item => ({
    year: item.year,
    count: item.count,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis
          dataKey="year"
          stroke="#9CA3AF"
          angle={-45}
          textAnchor="end"
          height={80}
          interval="preserveStartEnd"
        />
        <YAxis stroke="#9CA3AF" />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1F2937',
            border: '1px solid #4B5563',
            borderRadius: '8px',
            color: '#F3F4F6',
          }}
        />
        <Area
          type="monotone"
          dataKey="count"
          stroke="#60A5FA"
          fill="#3B82F6"
          fillOpacity={0.6}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
