interface WordCloudProps {
  words: { text: string; count: number }[];
}

export default function WordCloud({ words }: WordCloudProps) {
  if (words.length === 0) {
    return <div className="text-gray-400 text-center py-8">No words to display</div>;
  }

  const maxCount = Math.max(...words.map(w => w.count));
  const minSize = 14;
  const maxSize = 48;

  return (
    <div className="flex flex-wrap justify-center items-center gap-2 py-4 min-h-[300px]">
      {words.map((word, idx) => {
        const size = minSize + ((word.count / maxCount) * (maxSize - minSize));
        const opacity = 0.5 + (word.count / maxCount) * 0.5;

        return (
          <span
            key={idx}
            className="inline-block px-2 py-1 hover:text-purple-300 transition-all cursor-default"
            style={{
              fontSize: `${size}px`,
              opacity,
              color: `rgb(192, 132, 252, ${opacity})`,
            }}
            title={`${word.text}: ${word.count} occurrences`}
          >
            {word.text}
          </span>
        );
      })}
    </div>
  );
}
