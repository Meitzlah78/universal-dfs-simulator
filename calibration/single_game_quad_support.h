/* Binary128 arithmetic and native int64 graph serialization helpers. */
#include <quadmath.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {int64_t previous,next,ns,na,coord;int64_t *ss,*sd,*as,*ad;} Layer;
typedef struct {int64_t nl,final,nt;Layer *layers;int64_t *ti,*tf;} Node;
static void fail(const char *s){fprintf(stderr,"%s\n",s);exit(2);}
static void *alloc(size_t n){void *p=malloc(n?n:1);if(!p)fail("allocation failure");return p;}
static void readn(FILE *f,void *p,size_t size,size_t count){if(fread(p,size,count,f)!=count)fail("short graph input");}
static int64_t readi(FILE *f){int64_t v;readn(f,&v,8,1);return v;}
static int64_t *readv(FILE *f,int64_t n){int64_t *v=alloc(8*n);readn(f,v,8,n);return v;}
static double seconds(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+1e-9*t.tv_nsec;}
static double lsed(double x,double y){if(x==-INFINITY)return y;if(y==-INFINITY)return x;double m=fmax(x,y);return m+log1p(exp(-fabs(x-y)));}
static __float128 lseq(__float128 x,__float128 y){if(x==-HUGE_VALQ)return y;if(y==-HUGE_VALQ)return x;__float128 m=fmaxq(x,y);return m+log1pq(expq(-fabsq(x-y)));}

