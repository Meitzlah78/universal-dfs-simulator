/* All optimizer arithmetic and objective differences use GCC binary128.
 * Graph storage uses int64 indices; no binary128 array crosses a NumPy ABI.
 * A compact shared header defines graph storage and log-add arithmetic. */
#include "single_game_quad_support.h"
typedef __float128 Q;
#ifndef K
#define K 100
#endif
#ifndef ORIGINAL
#define ORIGINAL 128
#endif
#define MEMORY 5
typedef struct {Q eta[K],theta[K],mean[K],graw[K],g[K],original[ORIGINAL];Q value,z,mass,maxraw,maxoriginal,norm;} State;
static Node *graph;static int64_t nn,support,entries;
static Q B[K*K],inverse[K*K],D[K],chol[K*K],target[K],T[ORIGINAL*K],offset[ORIGINAL],original_target[ORIGINAL];
static int calls=0;static double started;static FILE *ledger;
static Q inner(const Q *a,const Q *b){Q s=0;for(int i=0;i<K;i++)s+=a[i]*b[i];return s;}
static void qfield(FILE *f,const char *name,Q x){char buf[128];quadmath_snprintf(buf,sizeof buf,"%.40Qg",x);fprintf(f,"\"%s\":\"%s\"",name,buf);}
static void qvector(FILE *f,const char *name,const Q *x,int n){fprintf(f,"\"%s\":[",name);for(int i=0;i<n;i++){char b[128];quadmath_snprintf(b,sizeof b,"%.40Qg",x[i]);fprintf(f,"%s\"%s\"",i?",":"",b);}fputc(']',f);}
static void node_moments(Node *node,const Q *theta,Q *z,Q *mean){
 Q **forward=alloc((node->nl+1)*sizeof(Q*));forward[0]=alloc(sizeof(Q));forward[0][0]=0;
 for(int64_t k=0;k<node->nl;k++){Layer *l=&node->layers[k];Q *out=alloc(l->next*sizeof(Q));forward[k+1]=out;
  for(int64_t j=0;j<l->next;j++)out[j]=-HUGE_VALQ;
  for(int64_t j=0;j<l->ns;j++)out[l->sd[j]]=lseq(out[l->sd[j]],forward[k][l->ss[j]]);
  Q potential=l->coord>=0?theta[l->coord]:0;
  for(int64_t j=0;j<l->na;j++)out[l->ad[j]]=lseq(out[l->ad[j]],forward[k][l->as[j]]+potential);
 }
 Q *weights=alloc(node->nt*sizeof(Q)),*potentials=alloc(node->nt*sizeof(Q)),maximum=-HUGE_VALQ;
 for(int64_t j=0;j<node->nt;j++){Q p=0;for(int h=0;h<3;h++){int64_t i=node->tf[3*j+h];if(i>=0)p+=theta[i];}
  potentials[j]=p;weights[j]=forward[node->nl][node->ti[j]]+p;if(weights[j]>maximum)maximum=weights[j];}
 Q sum=0;for(int64_t j=0;j<node->nt;j++)sum+=expq(weights[j]-maximum);*z=maximum+logq(sum);
 for(int i=0;i<K;i++)mean[i]=0;
 Q *tail=alloc(node->final*sizeof(Q));for(int64_t j=0;j<node->final;j++)tail[j]=-HUGE_VALQ;
 for(int64_t j=0;j<node->nt;j++){Q p=expq(weights[j]-*z);for(int h=0;h<3;h++){int64_t i=node->tf[3*j+h];if(i>=0)mean[i]+=p;}tail[node->ti[j]]=potentials[j];}
 for(int64_t k=node->nl-1;k>=0;k--){Layer *l=&node->layers[k];Q potential=l->coord>=0?theta[l->coord]:0;
  if(l->coord>=0){Q inclusion=0;for(int64_t j=0;j<l->na;j++)inclusion+=expq(forward[k][l->as[j]]+potential+tail[l->ad[j]]-*z);mean[l->coord]+=inclusion;}
  Q *previous=alloc(l->previous*sizeof(Q));for(int64_t j=0;j<l->previous;j++)previous[j]=-HUGE_VALQ;
  for(int64_t j=0;j<l->ns;j++)previous[l->ss[j]]=lseq(previous[l->ss[j]],tail[l->sd[j]]);
  for(int64_t j=0;j<l->na;j++)previous[l->as[j]]=lseq(previous[l->as[j]],potential+tail[l->ad[j]]);
  free(tail);tail=previous;
 }
 free(tail);free(weights);free(potentials);for(int64_t k=0;k<=node->nl;k++)free(forward[k]);free(forward);
}
static void evaluate(State *state){
 calls++;for(int j=0;j<K;j++){state->theta[j]=0;for(int i=0;i<K;i++)state->theta[j]+=B[i*K+j]*D[i]*state->eta[i];}
 Q *zs=alloc(nn*sizeof(Q)),*means=alloc(nn*K*sizeof(Q));
 for(int64_t n=0;n<nn;n++){node_moments(&graph[n],state->theta,&zs[n],&means[n*K]);
  if((n+1)%10==0){printf("{\"event\":\"subtree_progress\",\"evaluation\":%d,\"completed\":%ld,\"elapsed_seconds\":%.6f}\n",calls,(long)n+1,seconds()-started);fflush(stdout);}}
 Q maximum=-HUGE_VALQ;for(int64_t n=0;n<nn;n++)if(zs[n]>maximum)maximum=zs[n];Q sum=0;
 for(int64_t n=0;n<nn;n++)sum+=expq(zs[n]-maximum);state->z=maximum+logq(sum);
 state->mass=0;for(int i=0;i<K;i++)state->mean[i]=0;
 for(int64_t n=0;n<nn;n++){Q p=expq(zs[n]-state->z);state->mass+=p;for(int i=0;i<K;i++)state->mean[i]+=p*means[n*K+i];}
 free(zs);free(means);state->value=state->z-logq((Q)support);state->maxraw=0;
 for(int i=0;i<K;i++){state->value-=state->theta[i]*target[i];state->graw[i]=state->mean[i]-target[i];if(fabsq(state->graw[i])>state->maxraw)state->maxraw=fabsq(state->graw[i]);}
 for(int i=0;i<K;i++){state->g[i]=0;for(int j=0;j<K;j++)state->g[i]+=D[i]*B[i*K+j]*state->graw[j];}
 state->maxoriginal=0;for(int i=0;i<ORIGINAL;i++){state->original[i]=offset[i];for(int j=0;j<K;j++)state->original[i]+=T[i*K+j]*state->mean[j];Q error=fabsq(state->original[i]-original_target[i]);if(error>state->maxoriginal)state->maxoriginal=error;}
 state->norm=fabsq(state->mass-1);
 if(isnanq(state->value)||isinfq(state->value))fail("nonfinite quad objective");
 for(int i=0;i<K;i++)if(isnanq(state->graw[i])||isinfq(state->graw[i]))fail("nonfinite quad gradient");
}
static int passed(const State *s){return s->maxraw<=1e-9Q&&s->maxoriginal<=1e-8Q&&s->norm<=1e-12Q;}
static void record(FILE *f,const char *event,int iteration,const State *s,const State *base,Q alpha,Q slope){
 fprintf(f,"{\"event\":\"%s\",\"iteration\":%d,\"evaluation\":%d,\"elapsed_seconds\":%.9g,",event,iteration,calls,seconds()-started);
 qfield(f,"objective",s->value);fputc(',',f);qfield(f,"raw_gradient_max",s->maxraw);fputc(',',f);qfield(f,"original_residual_max",s->maxoriginal);fputc(',',f);qfield(f,"normalization_error",s->norm);
 if(base){fputc(',',f);qfield(f,"objective_difference",s->value-base->value);fputc(',',f);qfield(f,"alpha",alpha);fputc(',',f);qfield(f,"directional_derivative",slope);}
 fputc(',',f);qvector(f,"eta",s->eta,K);fputc(',',f);qvector(f,"raw_theta",s->theta,K);fputc(',',f);qvector(f,"raw_gradient",s->graw,K);fputc(',',f);qvector(f,"transformed_gradient",s->g,K);fputc(',',f);qvector(f,"mean",s->mean,K);fputc(',',f);qvector(f,"original_expectations",s->original,ORIGINAL);fprintf(f,"}\n");fflush(f);
}
static void solve_metric(const Q *rhs,Q *out){Q y[K];for(int i=0;i<K;i++){Q s=rhs[i];for(int j=0;j<i;j++)s-=chol[i*K+j]*y[j];y[i]=s/chol[i*K+i];}
 for(int i=K-1;i>=0;i--){Q s=y[i];for(int j=i+1;j<K;j++)s-=chol[j*K+i]*out[j];out[i]=s/chol[i*K+i];}}
static void read_graph(const char *path){FILE *f=fopen(path,"rb");if(!f)fail("missing graph");char magic[8];readn(f,magic,1,8);if(memcmp(magic,"NDPQ0001",8))fail("bad graph magic");
 nn=readi(f);int64_t np=readi(f),features=readi(f);support=readi(f);entries=readi(f);if(features!=K)fail("wrong feature count");
 double *points=alloc(np*K*sizeof(double)),td[K];readn(f,points,sizeof(double),np*K);free(points);readn(f,td,sizeof(double),K);int64_t *counts=readv(f,K);
 for(int i=0;i<K;i++)target[i]=(Q)counts[i]/(Q)entries;free(counts);graph=alloc(nn*sizeof(Node));
 for(int64_t n=0;n<nn;n++){Node *node=&graph[n];node->nl=readi(f);node->layers=alloc(node->nl*sizeof(Layer));for(int64_t k=0;k<node->nl;k++){Layer *l=&node->layers[k];l->previous=readi(f);l->next=readi(f);l->ns=readi(f);l->na=readi(f);l->coord=readi(f);l->ss=readv(f,l->ns);l->sd=readv(f,l->ns);l->as=readv(f,l->na);l->ad=readv(f,l->na);}node->final=readi(f);node->nt=readi(f);node->ti=readv(f,node->nt);node->tf=readv(f,node->nt*3);}fclose(f);}
static void read_optimizer(const char *path,State *state){FILE *f=fopen(path,"rb");if(!f)fail("missing optimizer input");char magic[8];readn(f,magic,1,8);if(memcmp(magic,"NQOPT001",8))fail("bad optimizer magic");
 double initial[K],scaling[K],h[K*K];readn(f,initial,sizeof(double),K);int64_t *b=readv(f,K*K),*inv=readv(f,K*K);readn(f,scaling,sizeof(double),K);readn(f,h,sizeof(double),K*K);
 for(int i=0;i<K*K;i++){B[i]=(Q)b[i];inverse[i]=(Q)inv[i];}free(b);free(inv);for(int i=0;i<K;i++)D[i]=(Q)scaling[i];
 int64_t *t=readv(f,ORIGINAL*K),*o=readv(f,ORIGINAL),*counts=readv(f,ORIGINAL);for(int i=0;i<ORIGINAL*K;i++)T[i]=(Q)t[i];for(int i=0;i<ORIGINAL;i++){offset[i]=(Q)o[i];original_target[i]=(Q)counts[i]/(Q)entries;}free(t);free(o);free(counts);fclose(f);
 for(int i=0;i<K;i++){state->eta[i]=0;for(int j=0;j<K;j++)state->eta[i]+=inverse[j*K+i]*(Q)initial[j];state->eta[i]/=D[i];}
 for(int i=0;i<K;i++)for(int j=0;j<K;j++){if(j>i){chol[i*K+j]=0;continue;}Q sum=((Q)h[i*K+j]+(Q)h[j*K+i])/2;for(int k=0;k<j;k++)sum-=chol[i*K+k]*chol[j*K+k];if(i==j){if(sum<=0)fail("saved Hessian metric is not positive definite");chol[i*K+j]=sqrtq(sum);}else chol[i*K+j]=sum/chol[j*K+j];}
}
int main(int argc,char **argv){if(argc<5)fail("usage: quad_refinement GRAPH OPT_INPUT EVENTS FINAL [validate]");
 if(FLT128_MANT_DIG!=113)fail("not a binary128 build");started=seconds();read_graph(argv[1]);State current={0};read_optimizer(argv[2],&current);ledger=fopen(argv[3],"wx");if(!ledger)fail("ledger exists or cannot create");
 int validation=argc>5;evaluate(&current);record(ledger,"initial",0,&current,NULL,0,0);record(stdout,"initial",0,&current,NULL,0,0);
 int accepted=0;char reason[160];strcpy(reason,validation?"validation only":(passed(&current)?"initial state passed gates":"refinement initialized"));
 Q S[MEMORY][K],Y[MEMORY][K],rho[MEMORY];int history=0;
 if(!validation)for(int iteration=1;iteration<=5&&!passed(&current);iteration++){
  if(calls>=12||seconds()-started>300){strcpy(reason,"bounded evaluation/time budget reached");break;}
  Q work[K],direction[K],coeff[MEMORY];memcpy(work,current.g,sizeof(work));
  for(int j=history-1;j>=0;j--){coeff[j]=rho[j]*inner(S[j],work);for(int i=0;i<K;i++)work[i]-=coeff[j]*Y[j][i];}
  solve_metric(work,direction);for(int j=0;j<history;j++){Q beta=rho[j]*inner(Y[j],direction);for(int i=0;i<K;i++)direction[i]+=S[j][i]*(coeff[j]-beta);}for(int i=0;i<K;i++)direction[i]=-direction[i];
  Q slope0=inner(current.g,direction);if(slope0>=0){strcpy(reason,"non-descent L-BFGS direction");break;}
  Q alpha=1,previous_alpha=0,lo=0,hi=0,lo_value=current.value,previous_value=current.value;int zoom=0,found=0;State trial;
  for(int attempt=0;attempt<8;attempt++){
   if(calls>=12||seconds()-started>300){strcpy(reason,"bounded evaluation/time budget reached in line search");break;}
   if(zoom)alpha=(lo+hi)/2;
   for(int i=0;i<K;i++)trial.eta[i]=current.eta[i]+alpha*direction[i];evaluate(&trial);Q slope=inner(trial.g,direction),delta=trial.value-current.value;
   record(ledger,"trial",iteration,&trial,&current,alpha,slope);
   int armijo=delta<=1e-4Q*alpha*slope0,curvature=fabsq(slope)<=.9Q*fabsq(slope0);
   if(armijo&&curvature){found=1;break;}
   if(!zoom){if(!armijo||(attempt>0&&trial.value>=previous_value)){lo=previous_alpha;lo_value=previous_value;hi=alpha;zoom=1;}
    else if(slope>=0){lo=alpha;lo_value=trial.value;hi=previous_alpha;zoom=1;}
    else{previous_alpha=alpha;previous_value=trial.value;alpha*=2;}}
   else{if(!armijo||trial.value>=lo_value)hi=alpha;else{if(slope*(hi-lo)>=0)hi=lo;lo=alpha;lo_value=trial.value;}}
  }
  if(!found){if(!strstr(reason,"budget"))strcpy(reason,"bounded strong-Wolfe search found no acceptable step");break;}
  Q s[K],y[K];for(int i=0;i<K;i++){s[i]=trial.eta[i]-current.eta[i];y[i]=trial.g[i]-current.g[i];}Q sy=inner(s,y);
  if(sy>0){if(history==MEMORY){memmove(S,S+1,(MEMORY-1)*K*sizeof(Q));memmove(Y,Y+1,(MEMORY-1)*K*sizeof(Q));memmove(rho,rho+1,(MEMORY-1)*sizeof(Q));history--;}
   memcpy(S[history],s,sizeof s);memcpy(Y[history],y,sizeof y);rho[history]=1/sy;history++;}
  record(ledger,"accepted",iteration,&trial,&current,alpha,inner(trial.g,direction));record(stdout,"accepted",iteration,&trial,&current,alpha,inner(trial.g,direction));current=trial;accepted++;
  strcpy(reason,passed(&current)?"accepted state passed original-unit gates":"accepted update; iteration limit may apply");
 }
 State fresh=current;evaluate(&fresh);record(ledger,"fresh_verification",accepted,&fresh,NULL,0,0);
 FILE *final=fopen(argv[4],"wx");if(!final)fail("final output exists or cannot create");record(final,"fresh_verification",accepted,&fresh,NULL,0,0);fclose(final);fclose(ledger);
 printf("{\"event\":\"termination\",\"status\":\"%s\",\"accepted_updates\":%d,\"evaluations_including_fresh\":%d,\"reason\":\"%s\",\"elapsed_seconds\":%.9g,\"validation_only\":%s}\n",passed(&fresh)?"verified_convergence":"stopped_without_verified_convergence",accepted,calls,reason,seconds()-started,validation?"true":"false");fflush(stdout);return 0;
}
