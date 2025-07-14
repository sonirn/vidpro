# Video Generation Website Requirements

## Website Logic Idea:
User upload sample video (max length 60s) (required), consistent character image (optional), audio file (optional).
Ai( use gemini 2.5 pro and 2.5 flash) analyse sample video in details(audio, video and visual in detail). Then understand what is about sample video exactly.Then check audio and character images (only if provided). Create a plan to make similar video as sample video.
After ai plan complete explain plan/idea (in text) to user. Give user option for regenerate idea and continue also user can chat to make specific changes in idea/plan.
Once user click continue then create video by following plan.( Use wan 2.1 ) Provide correct video ai model according video requirements. Make edits in video and give back similar video of sample video.combine small video, transition, effect and make final video ready. Allow users to download video without any logo and without any watermark in high quality.

## Requirements:
1. Video must be in 9:16 ratio
2. Must be similar final video as sample video.
3. Max length of final video must be less than 60s
4. Full process must be automatic.
5. Allow users to give idea, allow users to make changes in plan by chatting and regeneration option for idea.
6. Make sure sample video and results video script matches.
7. Make sure choose right video ai platform according sample video.
8. No watermark, no logo, high quality, no glitches.
9. Continuously show time remaining to get video.
10. Simple sign up with supabase without auth and without otp.
11. Make sure complete process on server.
12. Make sure user can access ready videos 7 day .
13. Process of generating video on server if user leave browser or leave website process must be continue.
14. Use cloudflare R2 to store video 
15. Once Started video genration it must be completed in any condition or until user cancel it.
16. Make sure once video genration started its must be in background. User can leave website/browser.
17. If user disconnect internet and video genration is on going it's must be continue.(Server side)
18. Make sure do not copy as it is same video
19. Do not use sample video visual as it is.
20. Do not use sample video audio use provided by user if user didn't provide then create custom
21. Make sure create similar video not copy of sample video or not accurate as sample video.
22. Mobile friendly interface only 
23. use gemini 2.5 pro and 2.5 flash
Use elevenlabs for audio (only if needed), use custom audio (only if provided)

## List of platforms:
Audio: 1. Elevenlabs (only for character voice and only if needed) 
Video:- 1.Implement wan 2.1 properly from open source and use to create small clips (deploy on server)

3. For combine clips and create final video (max 60s and 9:16) use ffmpeg or alternative 

## In short:
User add sample video=ai model(gemini) understand video= create plan to create similar video= show plan to user and take user opinion (if user tell for specific changes then do)= create shorts video (using video model wan 2.1)= combine all clips and make some editing (via ffmpeg or alternative )= give final video to user (must similar as sample video).

## API Keys:
1. Gork API (for analyse video sample through gemini or another model)
GROQ_API_KEY="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"

2. Eleven lab 
sk_613429b69a534539f725091aab14705a535bbeeeb6f52133

4. Gemini (use all multiple keys)( use gemini 2.5 pro and 2.5 flash)
API key:
1) AIzaSyBwVEDRvZ2bHppZj2zN4opMqxjzcxpJCDk 
2) AIzaSyB-VMWQe_Bvx6j_iixXTVGRB0fx0RpQSLU
3) AIzaSyD36dRBkEZUyCpDHLxTVuMO4P98SsYjkbc

5. Cloudflare R2 API
Account id
69317cc9622018bb255db5a590d143c2
API
https://69317cc9622018bb255db5a590d143c2.r2.cloudflarestorage.com

S3 client 
Access key
7804ed0f387a54af1eafbe2659c062f7
Secret access key
c94fe3a0d93c4594c8891b4f7fc54e5f26c76231972d8a4d0d8260bb6da61788

Token Value 
CYjagqmMcnNQaxSo6AdjUZBB5bslAXH6G8yYp4Mg

Endpoints 
https://69317cc9622018bb255db5a590d143c2.r2.cloudflarestorage.com

6. mongodb+srv://sonirn420:<Sonirn420>@debug.qprc9b.mongodb.net/?retryWrites=true&w=majority&appName=Debug

MCP CLOUD CLUSTER:
{
  "mcp": {
    "servers": {
      "MongoDB": {
        "type": "stdio",
        "command": "npx",
        "args": [
          "-y",
          "mongodb-mcp-server",
          "--connectionString",
          "mongodb+srv://sonirn420:<Sonirn420>@debug.qprc9b.mongodb.net/",
          "--readOnly"
        ]
      }
    }
  }
}

myVirtualDatabase
mongodb://atlas-sql-68705df40208293efaa90e92-qprc9b.a.query.mongodb.net/myVirtualDatabase?ssl=true&authSource=admin