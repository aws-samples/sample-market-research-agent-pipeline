import { S3Client, ListObjectsV2Command, GetObjectCommand, PutObjectCommand } from '@aws-sdk/client-s3';
import { getAWSConfig } from './authService';
import { S3NewsItem, CategoryNewsData, Category, NewsItem, SidebarItem } from '../types/newsletter.types';
import { fetchAuthSession } from 'aws-amplify/auth';


// Helper to title-case a string
const titleCase = (str: string): string =>
  str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();

// Convert a UTC Date to a human-readable IST string, e.g. "12 Mar 2026, 7:48 PM IST"
export const formatUtcToIst = (utcDate: Date): string => {
  const istDate = new Date(utcDate.getTime() + (5.5 * 60 * 60 * 1000));
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const formattedDate = `${istDate.getUTCDate()} ${monthNames[istDate.getUTCMonth()]} ${istDate.getUTCFullYear()}`;

  let hours = istDate.getUTCHours();
  const minutes = istDate.getUTCMinutes().toString().padStart(2, '0');
  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12 || 12;

  return `${formattedDate}, ${hours}:${minutes} ${ampm} IST`;
};

// Format a UTC timestamp string (e.g. "2026-03-12T15-57-21.123456Z" or ISO) to IST display string
export const formatTimestampToIst = (timestamp: string): string => {
  // Try the dashes-in-time format first
  const parsed = parseTimestamp(timestamp);
  if (parsed) return formatUtcToIst(parsed);
  // Fallback: standard ISO string
  const d = new Date(timestamp);
  if (!isNaN(d.getTime())) return formatUtcToIst(d);
  return timestamp;
};

// Parse a standard UTC timestamp string (e.g., 2026-03-12T15-57-21.123456Z)
const parseTimestamp = (str: string): Date | null => {
  // Check for new format: 2026-03-12T15-57-21.123456Z
  const stdMatch = str.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})/i);
  if (stdMatch) {
    const [, yr, mo, dy, hr, mn, sc] = stdMatch;
    return new Date(Date.UTC(
      Number.parseInt(yr), Number.parseInt(mo) - 1, Number.parseInt(dy),
      Number.parseInt(hr), Number.parseInt(mn), Number.parseInt(sc)
    ));
  }

  return null;
};

// Build a human-readable label for scheduled folders
const formatScheduledFolder = (topic: string, parts: string[]): string => {
  const frequency = parts[1] ? titleCase(parts[1]) : '';
  if (!frequency) return `${topic} - Scheduled`;

  const detail = parts[2];
  if (!detail) return `${topic} - Scheduled ${frequency}`;

  // If detail itself is a timestamp (daily runs), wrap it directly
  const detailTs = parseTimestamp(detail);
  if (detailTs) {
    return `${topic} - Scheduled ${frequency} (${formatUtcToIst(detailTs)})`;
  }

  const formattedDetail = /^\d+$/.test(detail) ? `Day ${detail}` : titleCase(detail);

  // Check for a trailing timestamp after the detail (e.g., wednesday_2026-03-12T...)
  const afterDetail = parts.slice(3).join('_');
  const afterTs = afterDetail ? parseTimestamp(afterDetail) : null;
  if (afterTs) {
    return `${topic} - Scheduled ${frequency} (${formattedDetail}) - ${formatUtcToIst(afterTs)}`;
  }

  return `${topic} - Scheduled ${frequency} (${formattedDetail})`;
};

// Format S3 folder name to human-readable format
// Handles three patterns:
//   1. Timestamp:  obesity_2024-03-01T12-00-00Z  → "Obesity - 1 Mar 2024, 5:30 PM IST"
//   2. Scheduler:  obesity_scheduled_weekly_wednesday_... → "Obesity - Scheduled Weekly (Wednesday)"
//   3. Multi-word: blood_pressure_scheduled_daily_... → "Blood Pressure - Scheduled Daily (...)"
export const formatFolderName = (folderName: string): string => {
  // Find where the topic name ends and metadata begins
  // Look for '_scheduled_' or a timestamp pattern '_YYYY-'
  const scheduledIdx = folderName.indexOf('_scheduled_');
  const timestampMatch = folderName.match(/_(\d{4}-\d{2}-\d{2}T)/);
  const timestampIdx = timestampMatch ? folderName.indexOf(timestampMatch[0]) : -1;

  // Determine the split point (earliest marker found)
  let splitIdx = -1;
  if (scheduledIdx >= 0 && timestampIdx >= 0) {
    splitIdx = Math.min(scheduledIdx, timestampIdx);
  } else if (scheduledIdx >= 0) {
    splitIdx = scheduledIdx;
  } else if (timestampIdx >= 0) {
    splitIdx = timestampIdx;
  }

  if (splitIdx < 0) return folderName;

  // Everything before the split is the topic (convert underscores back to spaces)
  const rawTopic = folderName.substring(0, splitIdx);
  const topic = rawTopic
    .split('_')
    .map((w) => titleCase(w))
    .join(' ');

  const remainder = folderName.substring(splitIdx + 1); // skip the leading '_'

  // ── Scheduler folders: scheduled_{frequency}[_{day}]_{timestamp} ──
  if (remainder.startsWith('scheduled_')) {
    return formatScheduledFolder(topic, remainder.split('_'));
  }

  // ── Timestamp folders: {YYYY-MM-DDTHH-MM-SS...} ──
  try {
    const dateMatch = remainder.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})/);
    if (!dateMatch) return folderName;

    const [, year, month, day, hour, minute, second] = dateMatch;
    const utcDate = new Date(Date.UTC(Number.parseInt(year), Number.parseInt(month) - 1, Number.parseInt(day), Number.parseInt(hour), Number.parseInt(minute), Number.parseInt(second)));

    return `${topic} - ${formatUtcToIst(utcDate)}`;
  } catch (error) {
    return folderName;
  }
};



// Extract and format just the run date from a topic folder name (e.g. "obesity_2026-03-25T10-07-43Z" → "25 Mar 2026")
export const extractRunDateFromTopic = (topic: string): string => {
  // For scheduled sub-folders the topic is "parent/child" – try on the child part first
  const part = topic.includes('/') ? topic.split('/').pop() ?? topic : topic;
  const ts = parseTimestamp(part);
  if (ts) {
    // Convert UTC to IST (+5:30) then format as "D Mon YYYY"
    const ist = new Date(ts.getTime() + 5.5 * 60 * 60 * 1000);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${ist.getUTCDate()} ${months[ist.getUTCMonth()]} ${ist.getUTCFullYear()}`;
  }
  return '';
};

// Initialize S3 client with authenticated Cognito credentials
const getS3Client = async (): Promise<S3Client> => {
  const config = getAWSConfig();

  try {
    // Get authenticated credentials from Amplify session
    const session = await fetchAuthSession();

    return new S3Client({
      region: config.region,
      credentials: session.credentials,
    });
  } catch (error) {
    console.error('Failed to get authenticated credentials:', error);
    throw error;
  }
};

// Detect if a folder name is a scheduled parent (contains "_scheduled_")
export const isScheduledFolder = (name: string): boolean =>
  name.toLowerCase().includes('_scheduled_');

// Parse S3 key to extract topic, category, and date
// On-demand format:  {topic}/{category}/{date}.json          (3 parts)
// Scheduled format:  {schedule}/{run}/{category}/{date}.json      (4 parts)
const parseS3Key = (key: string): { research_topic: string; category: Category; date: string } | null => {
  const parts = key.split('/');

  let category: string;
  let filename: string;
  let topic: string;

  if (parts.length === 3) {
    // On-demand: topic/category/file.json
    [topic, category, filename] = parts;
  } else if (parts.length === 4) {
    // Scheduled: schedule_folder/run_folder/category/file.json
    topic = `${parts[0]}/${parts[1]}`;
    category = parts[2];
    filename = parts[3];
  } else {
    return null;
  }

  const date = filename.replace('.json', '');
  if (category !== 'competitive_landscape' && category !== 'deals_and_partnerships') return null;

  return {
    research_topic: topic,
    category: category as Category,
    date,
  };
};

// Fetch and parse a single JSON object from S3
const fetchS3Object = async (bucket: string, key: string): Promise<NewsItem | null> => {
  try {
    const client = await getS3Client();
    const command = new GetObjectCommand({
      Bucket: bucket,
      Key: key,
      ResponseCacheControl: 'no-cache, no-store, must-revalidate',
    });

    const response = await client.send(command);
    const body = await response.Body?.transformToString();

    if (!body) return null;

    return JSON.parse(body) as NewsItem;
  } catch (error) {
    console.error('Error fetching S3 object:', key, error);
    return null;
  }
};

// Validate topic format to prevent XSS (allow / for nested scheduled prefixes)
const validateTopic = (topic: string): void => {
  if (!/^[a-zA-Z0-9_\-\s,/.]+$/.test(topic)) {
    throw new Error('Invalid topic format');
  }
};

// List all objects in a specific prefix (topic folder)
export const listNewsItems = async (topic: string): Promise<string[]> => {
  validateTopic(topic);

  const config = getAWSConfig();
  const client = await getS3Client();

  const command = new ListObjectsV2Command({
    Bucket: config.s3Bucket,
    Prefix: `${topic}/`,
  });

  try {
    const response = await client.send(command);
    return (response.Contents || [])
      .map((obj) => obj.Key)
      .filter((key): key is string => !!key && key.endsWith('.json'));
  } catch (error) {
    console.error('Error listing S3 objects:', error);
    throw error;
  }
};

// Fetch all news items for a specific topic and group by category
export const fetchBriefData = async (topic: string): Promise<CategoryNewsData> => {
  validateTopic(topic);

  const config = getAWSConfig();
  const keys = await listNewsItems(topic);

  const categoryData: CategoryNewsData = {
    competitive_landscape: [],
    deals_and_partnerships: [],
  };

  const fetchPromises = keys.map(async (key) => {
    const parsed = parseS3Key(key);
    if (!parsed) return null;

    const newsItem = await fetchS3Object(config.s3Bucket, key);
    if (!newsItem) return null;

    return {
      ...newsItem,
      research_topic: parsed.research_topic,
      category: parsed.category,
      date: newsItem.date || parsed.date, // Use date from JSON content, fallback to filename
      s3Key: key,
    } as S3NewsItem;
  });

  const results = await Promise.all(fetchPromises);

  results.forEach((item) => {
    if (item) {
      categoryData[item.category].push(item);
    }
  });

  // Sort by date (newest first)
  categoryData.competitive_landscape.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  categoryData.deals_and_partnerships.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  return categoryData;
};


// Refresh and get a single news letter after updation
export const refreshNewsItem = async (s3Key: string): Promise<S3NewsItem | null> => {

  const config = getAWSConfig();
  const parsed = parseS3Key(s3Key);
  if (!parsed) return null;

  const newsItem = await fetchS3Object(config.s3Bucket, s3Key);
  if (!newsItem) return null;

  return {
    ...newsItem,
    research_topic: parsed.research_topic,
    category: parsed.category,
    date: newsItem.date || parsed.date, // Use date from JSON content, fallback to filename
    s3Key,
  } as S3NewsItem;
};


// Get list of available topics (top-level folders)
export const listTopics = async (): Promise<string[]> => {

  const config = getAWSConfig();
  const client = await getS3Client();

  const command = new ListObjectsV2Command({
    Bucket: config.s3Bucket,
    Delimiter: '/',
  });

  try {
    const response = await client.send(command);
    return (response.CommonPrefixes || [])
      .map((prefix) => prefix.Prefix?.replace('/', ''))
      .filter((name): name is string => !!name);
  } catch (error) {
    console.error('Error listing topics:', error);
    throw error;
  }
};

// List sub-folders under a scheduled parent folder
export const listSubFolders = async (parentFolder: string): Promise<string[]> => {

  const config = getAWSConfig();
  const client = await getS3Client();

  const command = new ListObjectsV2Command({
    Bucket: config.s3Bucket,
    Prefix: `${parentFolder}/`,
    Delimiter: '/',
  });

  try {
    const response = await client.send(command);
    return (response.CommonPrefixes || [])
      .map((prefix) => prefix.Prefix?.replace(`${parentFolder}/`, '').replace('/', ''))
      .filter((name): name is string => !!name && name.length > 0);
  } catch (error) {
    console.error('Error listing sub-folders:', error);
    return [];
  }
};

// Build the sidebar tree: classify top-level folders and fetch sub-folders for scheduled ones
export const buildSidebarTree = async (topFolders: string[]): Promise<SidebarItem[]> => {
  const items: SidebarItem[] = [];

  for (const folder of topFolders) {
    if (isScheduledFolder(folder)) {
      // Scheduled parent → fetch child run folders
      const children = await listSubFolders(folder);
      items.push({
        name: folder,
        displayName: formatFolderName(folder),
        isScheduled: true,
        children: children.map((child) => ({
          name: `${folder}/${child}`,
          displayName: formatFolderName(child),
          isScheduled: false,
        })),
      });
    } else {
      // On-demand → flat item
      items.push({
        name: folder,
        displayName: formatFolderName(folder),
        isScheduled: false,
      });
    }
  }

  return items;
};



// Upload file to S3 with topic and date format: Topic_YYYY-MM-DDTHH-MM-SS.ffffffZ
export const uploadFileToS3 = async (
  file: File,
  topic: string,
  bucketName: string
): Promise<string> => {
  validateTopic(topic);

  const client = await getS3Client();
  const now = new Date();
  // Convert to IST (UTC+5:30)
  const istOffset = 5.5 * 60 * 60 * 1000;
  const istTime = new Date(now.getTime() + istOffset);
  const timestamp = istTime.toISOString().replace(/:/g, '-').replace(/\./g, '-');
  const fileName = `${topic}_${timestamp}`;

  // Convert File to ArrayBuffer for AWS SDK
  const fileBuffer = await file.arrayBuffer();

  const command = new PutObjectCommand({
    Bucket: bucketName,
    Key: fileName,
    Body: new Uint8Array(fileBuffer),
    ContentType: file.type || 'text/plain',
  });

  try {
    await client.send(command);
    console.log(`File uploaded successfully: ${fileName}`);
    return fileName;
  } catch (error) {
    console.error('Error uploading file to S3:', error);
    throw error;
  }
};

// Fetch Domains Config from VITE_DOMAINS_CONFIG_BUCKET
export const fetchDomainsConfig = async (): Promise<string[]> => {
  const config = getAWSConfig();
  if (!config.domainsConfigBucket) return [];

  const client = await getS3Client();
  const command = new ListObjectsV2Command({
    Bucket: config.domainsConfigBucket,
  });

  try {
    const response = await client.send(command);
    if (!response.Contents) return [];

    let allDomains: string[] = [];

    // Fetch all files
    const fetchPromises = response.Contents.map(async (obj) => {
      if (!obj.Key) return null;
      try {
        const getCmd = new GetObjectCommand({
          Bucket: config.domainsConfigBucket,
          Key: obj.Key,
          ResponseCacheControl: 'no-cache, no-store, must-revalidate',
        });
        const getResp = await client.send(getCmd);
        const body = await getResp.Body?.transformToString();
        if (body) {
          const parsed = JSON.parse(body);
          if (parsed.domains && Array.isArray(parsed.domains)) {
            return parsed.domains;
          }
        }
      } catch (e) {
        console.error('Error fetching domain file', obj.Key, e);
      }
      return null;
    });

    const results = await Promise.all(fetchPromises);
    results.forEach(res => {
      if (res) allDomains = [...allDomains, ...res];
    });

    const uniqueDomains = Array.from(new Set(allDomains));   //Remove duplications in the urls

    // Appending additional source URLs
    // Additional hardcoded domains can be added here
    uniqueDomains.push('https://www.crunchbase.com/');

    return uniqueDomains;
  } catch (error) {
    console.error('Error fetching domains config:', error);
    return [];
  }
};
